/** Sharing a link the way a phone expects to share one.
 *
 * Promoters work almost entirely from a smartphone, and "copy the link,
 * leave the app, open WhatsApp, paste" is three steps too many. Where the
 * browser supports it, `navigator.share()` opens the phone's own share
 * sheet (WhatsApp, Telegram, SMS, Mail, whatever the person actually has
 * installed) -- so we never hardcode a list of social networks, and the
 * user's own installed apps are always the list.
 *
 * Everything degrades: on a desktop browser, on http://, or when the user
 * dismisses the sheet, this falls back to copying to the clipboard, and
 * `result` tells the caller which of the two actually happened so the
 * button can say the truth ("Condiviso!" vs "Link copiato!").
 */

export type ShareResult = "shared" | "copied" | "failed";

type ShareInput = {
  url: string;
  /** Shown as the share sheet's title on platforms that display one. */
  title?: string;
  /** Message body pre-filled in WhatsApp/SMS/etc. alongside the link. */
  text?: string;
  /** Skip the native sheet and copy straight to the clipboard. Used by the
      dedicated "Copia link" button, which sits next to explicit WhatsApp /
      Telegram / Email buttons (see components/share-buttons.tsx): somebody
      pressing "Copia link" has already decided, and opening a share sheet
      instead would be answering a question they did not ask. */
  preferClipboard?: boolean;
};

export async function shareOrCopyLink({ url, title, text, preferClipboard = false }: ShareInput): Promise<ShareResult> {
  if (typeof navigator === "undefined") return "failed";

  // navigator.share exists but throws NotAllowedError outside a secure
  // context or outside a user gesture, and canShare() is not implemented
  // everywhere share() is -- so feature-detect loosely and let the catch
  // below handle the rest rather than trying to predict every browser.
  if (!preferClipboard && typeof navigator.share === "function") {
    try {
      await navigator.share({ url, title, text });
      return "shared";
    } catch (err) {
      // The user closing the share sheet is a deliberate "no thanks", not a
      // failure to route around: copying to the clipboard behind their back
      // would be the wrong answer.
      if (err instanceof DOMException && err.name === "AbortError") return "failed";
      // Anything else (unsupported payload, insecure context, no handler)
      // falls through to the clipboard.
    }
  }

  try {
    await navigator.clipboard.writeText(url);
    return "copied";
  } catch {
    return "failed";
  }
}
