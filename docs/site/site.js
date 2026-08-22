document.querySelectorAll(".copy-btn").forEach(function (button) {
  button.addEventListener("click", function () {
    var pre = button.closest(".code-block").querySelector("pre code");
    var text = pre.textContent;
    var label = button.querySelector(".copy-label");
    var originalText = label ? label.textContent : "";

    function showCopied() {
      if (label) {
        label.textContent = button.getAttribute("data-copied-label") || "Copied";
        setTimeout(function () {
          label.textContent = originalText;
        }, 1600);
      }
    }

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(showCopied, function () {
        fallbackCopy(text);
        showCopied();
      });
    } else {
      fallbackCopy(text);
      showCopied();
    }
  });
});

function fallbackCopy(text) {
  var textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  try {
    document.execCommand("copy");
  } catch (err) {
    /* clipboard unavailable; ignore */
  }
  document.body.removeChild(textarea);
}
