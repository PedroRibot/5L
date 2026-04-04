(function () {
    var saved = localStorage.getItem("accentHue");
    if (saved !== null) {
        var hue = parseInt(saved, 10);
        var accent = hue === 0 ? "#ffffff" : "hsl(" + hue + ", 100%, 50%)";
        document.documentElement.style.setProperty("--accent", accent);
    }
})();

// Shared helper: parse --accent into [r, g, b] for canvas use
function getAccentRGB() {
    var v = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim();
    var tmp = document.createElement("canvas").getContext("2d");
    tmp.fillStyle = v;
    var hex = tmp.fillStyle;
    return [
        parseInt(hex.slice(1, 3), 16),
        parseInt(hex.slice(3, 5), 16),
        parseInt(hex.slice(5, 7), 16)
    ];
}
