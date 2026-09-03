import importlib.util
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("bookmark_tls", ROOT / "scripts" / "manage.py")
manage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manage)


class UpdateTLSTests(TestCase):
    def test_windows_uses_system_certificates_for_both_update_hosts_only(self):
        for _, url in manage.UPDATE_SOURCES:
            with self.subTest(url=url), patch.object(manage.sys, "platform", "win32"), patch.dict(
                manage.os.environ, {"GIT_SSL_NO_VERIFY": "1", "GIT_SSL_CAINFO": "custom-ca.pem"}
            ), patch.object(manage.subprocess, "run", return_value=manage.subprocess.CompletedProcess([], 0, "ok", "")) as run:
                self.assertEqual(manage.git_output("fetch", url, "main", network_url=url), "ok")
                command = run.call_args.args[0]
                self.assertEqual(command, [
                    "git", "-c", f"http.{url}.sslVerify=true",
                    "-c", f"http.{url}.sslBackend=schannel",
                    "-c", f"http.{url}.schannelUseSSLCAInfo=false", "fetch", url, "main",
                ])
                self.assertNotIn("GIT_SSL_NO_VERIFY", run.call_args.kwargs["env"])
                self.assertEqual(run.call_args.kwargs["env"]["GIT_SSL_CAINFO"], "custom-ca.pem")
                self.assertEqual(manage.os.environ["GIT_SSL_NO_VERIFY"], "1", "不能修改进程外的 Git 配置")
                self.assertNotIn("sslVerify=false", " ".join(command))

    def test_other_platforms_preserve_tls_backend_but_keep_verification_on(self):
        url = manage.UPDATE_SOURCES[0][1]
        for platform in ("darwin", "linux"):
            with self.subTest(platform=platform), patch.object(manage.sys, "platform", platform), patch.object(
                manage.subprocess, "run", return_value=manage.subprocess.CompletedProcess([], 0, "ok", "")
            ) as run:
                manage.git_output("fetch", url, "main", network_url=url)
                self.assertEqual(run.call_args.args[0], ["git", "-c", f"http.{url}.sslVerify=true", "fetch", url, "main"])

    def test_certificate_failures_are_specific_without_exposing_raw_stderr(self):
        for detail in (
            "SSL certificate problem: unable to get local issuer certificate",
            "server certificate verification failed",
            "schannel: SEC_E_UNTRUSTED_ROOT (0x80090325) - untrusted certificate",
            "CERT_E_EXPIRED", "TRUST_E_CERT_SIGNATURE", "CERT_TRUST_REVOCATION_STATUS_UNKNOWN",
            "SEC_E_UNTRUSTED_ROOT", "SEC_E_CERT_EXPIRED", "SEC_E_WRONG_PRINCIPAL", "CRYPT_E_REVOCATION_OFFLINE",
        ):
            with self.subTest(detail=detail), patch.object(manage.subprocess, "run", return_value=manage.subprocess.CompletedProcess(
                [], 128, "", detail + " https://user:private-password@example.invalid"
            )):
                with self.assertRaises(manage.UpdateError) as caught:
                    manage.git_output("fetch", network_url=manage.UPDATE_SOURCES[0][1])
                self.assertEqual(caught.exception.code, "certificate_error")
                self.assertIn("证书验证失败", str(caught.exception))
                self.assertNotIn("private-password", str(caught.exception))

    def test_unsupported_schannel_never_retries_without_verification(self):
        with patch.object(manage.sys, "platform", "win32"), patch.object(manage.subprocess, "run", return_value=manage.subprocess.CompletedProcess(
            [], 128, "", "fatal: Unsupported SSL backend 'schannel'. Supported SSL backends: openssl"
        )) as run:
            with self.assertRaises(manage.UpdateError) as caught:
                manage.git_output("fetch", network_url=manage.UPDATE_SOURCES[0][1])
        self.assertEqual(caught.exception.code, "tls_backend")
        self.assertIn("Git for Windows", str(caught.exception))
        self.assertEqual(run.call_count, 1)

    def test_network_timeout_is_not_reported_as_a_certificate_failure(self):
        with patch.object(manage.subprocess, "run", side_effect=manage.subprocess.TimeoutExpired("git", 15)):
            with self.assertRaises(manage.UpdateError) as caught:
                manage.git_output("fetch", network_url=manage.UPDATE_SOURCES[0][1])
        self.assertEqual(caught.exception.code, "network_timeout")

    def test_certificate_failure_on_gitee_can_still_fall_back_to_github(self):
        with patch.object(manage, "git_output", side_effect=[
            "main", "", manage.UpdateError("证书验证失败", "certificate_error"), "", "same", "same",
        ]):
            status = manage.repository_update_status()
        self.assertEqual(status["source"], "GitHub")
        self.assertNotIn("error", status)

    def test_all_sources_failing_preserve_certificate_reason_for_frontend(self):
        for code in ("certificate_error", "tls_backend"):
            with self.subTest(code=code), patch.object(manage, "git_output", side_effect=[
                "main", "", manage.UpdateError("证书故障", code), manage.UpdateError("网络超时", "network_timeout"),
            ]):
                with self.assertRaises(manage.UpdateError) as caught:
                    manage.repository_update_status()
                self.assertEqual(caught.exception.code, code)
                self.assertIn("Gitee：证书故障", str(caught.exception))
                self.assertIn("GitHub：网络超时", str(caught.exception))
