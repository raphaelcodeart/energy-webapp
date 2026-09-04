"use client";

import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { PhotoUpload } from "@/components/photo-upload";
import { friendlyApiError } from "@/lib/api-error";
import type { DocumentationPostRead } from "@/lib/types";

const AUDIENCE_LABELS: Record<string, string> = {
  CUSTOMER: "Solo clienti",
  PROMOTER: "Solo promoter",
  BOTH: "Clienti e promoter",
};
const AUDIENCE_COLORS: Record<string, string> = {
  CUSTOMER: "bg-sky-500/10 text-sky-400 border-sky-500/20",
  PROMOTER: "bg-orange-500/10 text-orange-400 border-orange-500/20",
  BOTH: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
};
const STATUS_LABELS: Record<string, string> = { PUBLISHED: "Pubblicato", ARCHIVED: "Archiviato" };

async function fetchPosts(): Promise<DocumentationPostRead[]> {
  const res = await fetch("/api/proxy/documentation/admin");
  if (!res.ok) throw new Error(await friendlyApiError(res));
  return res.json();
}

/** Minimal single-file uploader for the PDF attachment -- PhotoUpload only
 * handles images (accept="image/*", reads back .photo_url/.image_url); a PDF
 * needs its own accept filter and reads back .pdf_url/.pdf_filename instead,
 * not worth generalizing PhotoUpload for a single extra caller. */
function PdfUpload({ postId, currentFilename, onUploaded }: { postId: string; currentFilename: string | null; onUploaded: (pdfUrl: string, filename: string) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(null);
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch(`/api/proxy/documentation/${postId}/pdf`, { method: "POST", body: formData });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const updated: DocumentationPostRead = await res.json();
      if (updated.pdf_url) onUploaded(updated.pdf_url, updated.pdf_filename ?? file.name);
    } catch (err: any) {
      setError(err.message || "Caricamento PDF fallito. Riprova.");
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <div className="space-y-1">
      <input ref={inputRef} type="file" accept="application/pdf" onChange={handleFileChange} className="hidden" id={`pdf-input-${postId}`} />
      <label
        htmlFor={`pdf-input-${postId}`}
        className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold bg-white/5 light:bg-slate-900/5 hover:bg-white/10 border border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 cursor-pointer transition"
      >
        {uploading ? "Caricamento..." : currentFilename ? `Sostituisci PDF (${currentFilename})` : "Carica PDF"}
      </label>
      {error && <p className="text-[11px] text-rose-400">{error}</p>}
    </div>
  );
}

export function AdminDocumentationPanel() {
  const queryClient = useQueryClient();
  const { data: posts, error: loadError } = useQuery({
    queryKey: ["admin", "documentation"],
    queryFn: fetchPosts,
  });

  const [showCreate, setShowCreate] = useState(false);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [audience, setAudience] = useState("BOTH");
  const [videoUrl, setVideoUrl] = useState("");
  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const [editingPost, setEditingPost] = useState<DocumentationPostRead | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editBody, setEditBody] = useState("");
  const [editAudience, setEditAudience] = useState("BOTH");
  const [editVideoUrl, setEditVideoUrl] = useState("");
  const [editImageUrl, setEditImageUrl] = useState<string | null>(null);
  const [editPdfUrl, setEditPdfUrl] = useState<string | null>(null);
  const [editPdfFilename, setEditPdfFilename] = useState<string | null>(null);
  const [editLoading, setEditLoading] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  const [deletingPost, setDeletingPost] = useState<DocumentationPostRead | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  function openEdit(p: DocumentationPostRead) {
    setEditTitle(p.title);
    setEditBody(p.body ?? "");
    setEditAudience(p.audience);
    setEditVideoUrl(p.video_url ?? "");
    setEditImageUrl(p.image_url);
    setEditPdfUrl(p.pdf_url);
    setEditPdfFilename(p.pdf_filename);
    setEditError(null);
    setEditingPost(p);
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreateLoading(true);
    setCreateError(null);
    try {
      const res = await fetch("/api/proxy/documentation", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, body: body || null, audience, video_url: videoUrl || null }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      const created: DocumentationPostRead = await res.json();
      setShowCreate(false);
      setTitle("");
      setBody("");
      setAudience("BOTH");
      setVideoUrl("");
      await queryClient.invalidateQueries({ queryKey: ["admin", "documentation"] });
      // Jump straight into editing so the admin can attach image/PDF right away.
      openEdit(created);
    } catch (err: any) {
      setCreateError(err.message || "Impossibile creare il post.");
    } finally {
      setCreateLoading(false);
    }
  }

  async function handleEditSave(e: React.FormEvent) {
    e.preventDefault();
    if (!editingPost) return;
    setEditLoading(true);
    setEditError(null);
    try {
      const res = await fetch(`/api/proxy/documentation/${editingPost.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: editTitle,
          body: editBody || null,
          audience: editAudience,
          video_url: editVideoUrl || null,
        }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setEditingPost(null);
      await queryClient.invalidateQueries({ queryKey: ["admin", "documentation"] });
    } catch (err: any) {
      setEditError(err.message || "Impossibile salvare le modifiche.");
    } finally {
      setEditLoading(false);
    }
  }

  async function handleToggleStatus(p: DocumentationPostRead) {
    const newStatus = p.status === "PUBLISHED" ? "ARCHIVED" : "PUBLISHED";
    try {
      const res = await fetch(`/api/proxy/documentation/${p.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: newStatus }),
      });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      await queryClient.invalidateQueries({ queryKey: ["admin", "documentation"] });
    } catch {
      // Surfaced via the list reloading unchanged; not worth a dedicated banner
      // for a single-click toggle the admin can just retry.
    }
  }

  async function handleDelete() {
    if (!deletingPost) return;
    setDeleteLoading(true);
    setDeleteError(null);
    try {
      const res = await fetch(`/api/proxy/documentation/${deletingPost.id}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await friendlyApiError(res));
      setDeletingPost(null);
      await queryClient.invalidateQueries({ queryKey: ["admin", "documentation"] });
    } catch (err: any) {
      setDeleteError(err.message || "Impossibile eliminare il post.");
    } finally {
      setDeleteLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-xs text-slate-400 light:text-slate-500 max-w-2xl">
          Pubblica materiale per i clienti (guide, novità) o per i promoter (listini, materiale formativo) --
          scegli per ognuno chi lo vede. Come un post: testo, e facoltativamente una foto, un PDF da scaricare e un link video.
        </p>
        <button
          onClick={() => setShowCreate(true)}
          className="shrink-0 px-4 py-2 rounded-xl text-xs font-semibold bg-orange-600 hover:bg-orange-500 text-white shadow-lg shadow-orange-500/20 transition cursor-pointer"
        >
          + Nuovo Post
        </button>
      </div>

      {loadError && <p className="text-sm text-rose-400">Impossibile caricare la documentazione.</p>}

      <div className="grid gap-4 sm:grid-cols-2">
        {posts === undefined ? (
          <p className="text-sm text-slate-500 col-span-2 text-center py-8">Caricamento...</p>
        ) : posts.length === 0 ? (
          <p className="text-sm text-slate-500 col-span-2 text-center py-8">Nessun post pubblicato ancora.</p>
        ) : (
          posts.map((p) => (
            <div key={p.id} className="glass-card rounded-2xl border-white/5 light:border-slate-200 bg-slate-950/40 light:bg-white/70 overflow-hidden flex flex-col">
              {p.image_url && (
                // eslint-disable-next-line @next/next/no-img-element -- externally-hosted, variable-source uploaded photo
                <img src={p.image_url} alt="" className="w-full h-36 object-cover" />
              )}
              <div className="p-5 flex flex-col gap-2 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${AUDIENCE_COLORS[p.audience]}`}>
                    {AUDIENCE_LABELS[p.audience]}
                  </span>
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${p.status === "PUBLISHED" ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" : "bg-slate-500/10 text-slate-400 border-slate-500/20"}`}>
                    {STATUS_LABELS[p.status]}
                  </span>
                </div>
                <h3 className="text-sm font-bold text-white light:text-slate-900">{p.title}</h3>
                {p.body && <p className="text-xs text-slate-400 light:text-slate-500 line-clamp-3 whitespace-pre-wrap">{p.body}</p>}
                <div className="flex items-center gap-3 text-[10px] text-slate-500 mt-1">
                  {p.pdf_url && <span>📎 PDF allegato</span>}
                  {p.video_url && <span>🎬 Video allegato</span>}
                  <span className="ml-auto">{new Date(p.created_at).toLocaleDateString("it-IT")}</span>
                </div>
                <div className="flex items-center gap-2 mt-3 pt-3 border-t border-white/5 light:border-slate-200">
                  <button
                    onClick={() => openEdit(p)}
                    className="px-2.5 py-1.5 rounded-lg bg-orange-600/10 hover:bg-orange-600/20 border border-orange-500/20 text-orange-400 text-xs font-semibold transition cursor-pointer"
                  >
                    Modifica
                  </button>
                  <button
                    onClick={() => handleToggleStatus(p)}
                    className="px-2.5 py-1.5 rounded-lg bg-white/5 light:bg-slate-900/5 hover:bg-white/10 border border-white/10 light:border-slate-300 text-slate-300 light:text-slate-600 text-xs font-semibold transition cursor-pointer"
                  >
                    {p.status === "PUBLISHED" ? "Archivia" : "Ripubblica"}
                  </button>
                  <button
                    onClick={() => setDeletingPost(p)}
                    className="ml-auto px-2.5 py-1.5 rounded-lg bg-rose-600/10 hover:bg-rose-600/20 border border-rose-500/20 text-rose-400 text-xs font-semibold transition cursor-pointer"
                  >
                    Elimina
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-lg glass-card rounded-2xl p-6 border-white/10 light:border-slate-300 bg-slate-950 light:bg-white animate-scale-up max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-white light:text-slate-900">Nuovo Post</h3>
              <button onClick={() => setShowCreate(false)}
                className="p-1 hover:bg-white/5 rounded-lg text-slate-400 light:text-slate-500 hover:text-white transition cursor-pointer">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <form onSubmit={handleCreate} className="space-y-4">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Titolo</label>
                <input required value={title} onChange={(e) => setTitle(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Testo</label>
                <textarea rows={4} value={body} onChange={(e) => setBody(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500 resize-none" />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Chi lo vede</label>
                <select value={audience} onChange={(e) => setAudience(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-slate-900 light:bg-white focus:border-orange-500">
                  <option value="BOTH">Clienti e promoter</option>
                  <option value="CUSTOMER">Solo clienti</option>
                  <option value="PROMOTER">Solo promoter</option>
                </select>
              </div>
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Link video (opzionale)</label>
                <input type="url" value={videoUrl} onChange={(e) => setVideoUrl(e.target.value)}
                  placeholder="https://youtube.com/..."
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
              </div>
              <p className="text-[11px] text-slate-500">Dopo aver creato il post potrai allegare una foto e un PDF.</p>

              {createError && (
                <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{createError}</div>
              )}

              <div className="flex justify-end gap-3 mt-4">
                <button type="button" onClick={() => setShowCreate(false)}
                  className="px-4 py-2 rounded-xl bg-white/5 light:bg-slate-900/5 hover:bg-white/10 text-xs font-semibold text-slate-300 light:text-slate-600 border border-white/5 light:border-slate-200 transition cursor-pointer">
                  Annulla
                </button>
                <button type="submit" disabled={createLoading}
                  className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50">
                  {createLoading ? "Creazione..." : "Crea Post"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {editingPost && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-lg glass-card rounded-2xl p-6 border-white/10 light:border-slate-300 bg-slate-950 light:bg-white animate-scale-up max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-white light:text-slate-900">Modifica Post</h3>
              <button onClick={() => setEditingPost(null)}
                className="p-1 hover:bg-white/5 rounded-lg text-slate-400 light:text-slate-500 hover:text-white transition cursor-pointer">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="mb-5 pb-5 border-b border-white/5 light:border-slate-200 space-y-4">
              <div>
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block mb-2">Foto</label>
                <PhotoUpload
                  currentUrl={editImageUrl}
                  uploadPath={`documentation/${editingPost.id}/image`}
                  onUploaded={(url) => {
                    setEditImageUrl(url);
                    queryClient.invalidateQueries({ queryKey: ["admin", "documentation"] });
                  }}
                  alt={editingPost.title}
                  size={64}
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block mb-2">PDF</label>
                <PdfUpload
                  postId={editingPost.id}
                  currentFilename={editPdfFilename}
                  onUploaded={(url, filename) => {
                    setEditPdfUrl(url);
                    setEditPdfFilename(filename);
                    queryClient.invalidateQueries({ queryKey: ["admin", "documentation"] });
                  }}
                />
              </div>
            </div>

            <form onSubmit={handleEditSave} className="space-y-4">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Titolo</label>
                <input required value={editTitle} onChange={(e) => setEditTitle(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Testo</label>
                <textarea rows={4} value={editBody} onChange={(e) => setEditBody(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500 resize-none" />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Chi lo vede</label>
                <select value={editAudience} onChange={(e) => setEditAudience(e.target.value)}
                  className="w-full rounded-xl glass-input px-3 py-2.5 text-sm bg-slate-900 light:bg-white focus:border-orange-500">
                  <option value="BOTH">Clienti e promoter</option>
                  <option value="CUSTOMER">Solo clienti</option>
                  <option value="PROMOTER">Solo promoter</option>
                </select>
              </div>
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-300 light:text-slate-600 uppercase block">Link video (opzionale)</label>
                <input type="url" value={editVideoUrl} onChange={(e) => setEditVideoUrl(e.target.value)}
                  placeholder="https://youtube.com/..."
                  className="w-full rounded-xl glass-input px-3 py-2 text-sm focus:border-orange-500" />
              </div>

              {editError && (
                <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs">{editError}</div>
              )}

              <div className="flex justify-end gap-3 mt-4">
                <button type="button" onClick={() => setEditingPost(null)}
                  className="px-4 py-2 rounded-xl bg-white/5 light:bg-slate-900/5 hover:bg-white/10 text-xs font-semibold text-slate-300 light:text-slate-600 border border-white/5 light:border-slate-200 transition cursor-pointer">
                  Chiudi
                </button>
                <button type="submit" disabled={editLoading}
                  className="px-4 py-2 rounded-xl bg-orange-600 hover:bg-orange-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50">
                  {editLoading ? "Salvataggio..." : "Salva Modifiche"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {deletingPost && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 light:bg-slate-900/40 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-md glass-card rounded-2xl p-6 border-white/10 light:border-slate-300 bg-slate-950 light:bg-white animate-scale-up">
            <h3 className="text-lg font-bold text-white light:text-slate-900 mb-2">Eliminare &ldquo;{deletingPost.title}&rdquo;?</h3>
            <p className="text-xs text-slate-400 light:text-slate-500 mb-4">
              Il post sparirà subito dal feed di chi lo vedeva. Questa azione non si può annullare.
            </p>
            {deleteError && (
              <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs mb-4">{deleteError}</div>
            )}
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setDeletingPost(null)}
                className="px-4 py-2 rounded-xl bg-white/5 light:bg-slate-900/5 hover:bg-white/10 text-xs font-semibold text-slate-300 light:text-slate-600 border border-white/5 light:border-slate-200 transition cursor-pointer"
              >
                Annulla
              </button>
              <button
                onClick={handleDelete}
                disabled={deleteLoading}
                className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-xs font-semibold text-white transition cursor-pointer disabled:opacity-50"
              >
                {deleteLoading ? "Eliminazione..." : "Elimina"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
