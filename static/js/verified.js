// Clear any redirect credentials without reading, storing, or sending them.
if (window.location.search || window.location.hash) {
    const callbackUrl = document.getElementById("verification-card").dataset.callbackUrl;
    window.history.replaceState(null, "", callbackUrl);
}
