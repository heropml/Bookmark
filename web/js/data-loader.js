const dataVersion = new URLSearchParams(window.location.search).get("v") || "";
document.write('<script src="data.example.js?v=' + encodeURIComponent(dataVersion) + '"><\/script>');
document.write('<script src="data.js?v=' + encodeURIComponent(dataVersion) + '"><\/script>');
