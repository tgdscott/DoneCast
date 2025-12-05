export async function copyTextToClipboard(text) {
  if (!text) {
    return false;
  }

  try {
    if (navigator?.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch (err) {
    console.warn("[Clipboard] navigator.clipboard failed:", err);
  }

  try {
    const textArea = document.createElement("textarea");
    textArea.value = text;
    textArea.style.position = "fixed";
    textArea.style.top = "-1000px";
    textArea.style.left = "-1000px";
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    const succeeded = document.execCommand("copy");
    document.body.removeChild(textArea);
    return succeeded;
  } catch (fallbackErr) {
    console.error("[Clipboard] Fallback copy failed:", fallbackErr);
    return false;
  }
}
