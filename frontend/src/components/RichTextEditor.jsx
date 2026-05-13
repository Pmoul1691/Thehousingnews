import React, { useEffect, useRef, useState, useCallback } from "react";
import { useEditor, EditorContent } from "@tiptap/react";
import { BubbleMenu } from "@tiptap/react/menus";
import StarterKit from "@tiptap/starter-kit";
import Link from "@tiptap/extension-link";
import Image from "@tiptap/extension-image";
import Youtube from "@tiptap/extension-youtube";
import { Markdown } from "tiptap-markdown";

import api, { API } from "@/lib/api";
import { toast } from "sonner";

/**
 * Rich-text essay editor. Stores content as Markdown (round-trip via tiptap-markdown).
 * Calls `onChange(markdownString)` whenever the document changes.
 * Toolbar: bold / italic / H1-H2 / quote / list / link / image / video / audio / YouTube embed.
 * Slash-command menu: type `/` at the start of a line to insert blocks.
 */
export default function RichTextEditor({ value, onChange, placeholder }) {
  const [uploadKind, setUploadKind] = useState("");
  const fileInputRef = useRef(null);
  const lastEmittedRef = useRef("");

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: { levels: [1, 2, 3] },
        codeBlock: { HTMLAttributes: { class: "essay-code" } },
      }),
      Link.configure({
        openOnClick: false,
        HTMLAttributes: { rel: "noopener noreferrer", target: "_blank" },
        autolink: true,
      }),
      Image.configure({ inline: false, allowBase64: false, HTMLAttributes: { class: "rounded-sm border hairline" } }),
      Youtube.configure({ controls: true, modestBranding: true, width: 640, height: 360 }),
      Markdown.configure({
        html: false,
        tightLists: true,
        bulletListMarker: "-",
        linkify: true,
        breaks: false,
        transformPastedText: true,
        transformCopiedText: true,
      }),
    ],
    content: value || "",
    onUpdate({ editor }) {
      try {
        const md = editor.storage.markdown.getMarkdown();
        lastEmittedRef.current = md;
        onChange && onChange(md);
      } catch (e) { /* ignore */ }
    },
    editorProps: {
      attributes: {
        "data-testid": "rich-editor",
        class: "essay-body prose-serif text-base sm:text-lg leading-relaxed min-h-[280px] focus:outline-none",
      },
    },
  });

  // Replace the document only when an externally-provided value diverges from our last emit
  useEffect(() => {
    if (!editor) return;
    if (value === lastEmittedRef.current) return;
    try {
      editor.commands.setContent(value || "", false);
    } catch (e) { /* ignore */ }
  }, [value, editor]);

  const uploadMedia = useCallback(async (file, kind) => {
    if (!file || !editor) return;
    setUploadKind(kind);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("kind", "posts");
      const r = await api.post("/uploads", fd, { headers: { "Content-Type": "multipart/form-data" } });
      const url = `${API}/uploads/file/${r.data.path}`;
      if (kind === "image") {
        editor.chain().focus().setImage({ src: url, alt: "" }).run();
      } else if (kind === "video") {
        const poster = r.data.thumbnail_path ? `${API}/uploads/file/${r.data.thumbnail_path}` : "";
        const html = `<p><video controls playsinline preload="metadata" src="${url}" poster="${poster}" style="max-width:100%;border:1px solid #E8D4A0;border-radius:2px;background:#000;"></video></p>`;
        editor.chain().focus().insertContent(html).run();
      } else if (kind === "audio") {
        const html = `<p><audio controls preload="metadata" src="${url}" style="width:100%"></audio></p>`;
        editor.chain().focus().insertContent(html).run();
      }
      toast.success(`${kind[0].toUpperCase()}${kind.slice(1)} inserted`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Upload failed");
    } finally { setUploadKind(""); }
  }, [editor]);

  const promptLink = () => {
    if (!editor) return;
    const prev = editor.getAttributes("link").href || "";
    const url = window.prompt("Link URL", prev);
    if (url === null) return;
    if (url === "") {
      editor.chain().focus().extendMarkRange("link").unsetLink().run();
      return;
    }
    editor.chain().focus().extendMarkRange("link").setLink({ href: url }).run();
  };

  const promptYouTube = () => {
    if (!editor) return;
    const url = window.prompt("YouTube or Vimeo URL");
    if (!url) return;
    api.post("/uploads/embed", { url })
      .then((r) => {
        if (r.data.provider === "youtube") {
          editor.chain().focus().setYoutubeVideo({ src: r.data.embed_url }).run();
        } else {
          // Vimeo: insert iframe via raw HTML
          const html = `<p><iframe src="${r.data.embed_url}" width="640" height="360" frameborder="0" allow="autoplay; fullscreen; picture-in-picture" allowfullscreen></iframe></p>`;
          editor.chain().focus().insertContent(html).run();
        }
        toast.success(`${r.data.provider} video inserted`);
      })
      .catch((e) => toast.error(e?.response?.data?.detail || "Could not parse URL"));
  };

  const openFile = (kind) => {
    if (!fileInputRef.current) return;
    fileInputRef.current.dataset.kind = kind;
    if (kind === "image") fileInputRef.current.accept = "image/*";
    else if (kind === "video") fileInputRef.current.accept = "video/mp4,video/quicktime,video/webm";
    else if (kind === "audio") fileInputRef.current.accept = "audio/*";
    fileInputRef.current.click();
  };

  const onFile = (e) => {
    const file = e.target.files?.[0];
    const kind = e.target.dataset.kind;
    e.target.value = "";
    if (file && kind) uploadMedia(file, kind);
  };

  // Slash command: when the user types "/" at the start of an empty paragraph, show a popover.
  const [slashOpen, setSlashOpen] = useState(false);
  const [slashCoords, setSlashCoords] = useState({ top: 0, left: 0 });
  const containerRef = useRef(null);

  useEffect(() => {
    if (!editor) return;
    const handle = () => {
      const { state } = editor;
      const { from, $from } = state.selection;
      const text = $from.parent.textContent;
      // Trigger when "/" was just typed: either an empty paragraph that contains only "/",
      // OR a paragraph whose character right before the cursor is "/" preceded by a space or start.
      const charBefore = text.slice(Math.max(0, $from.parentOffset - 1), $from.parentOffset);
      const charBeforeThat = $from.parentOffset >= 2 ? text.slice($from.parentOffset - 2, $from.parentOffset - 1) : "";
      const isStartSlash = text === "/" && $from.parent.type.name === "paragraph";
      const isMidlineSlash = charBefore === "/" && (charBeforeThat === "" || /\s/.test(charBeforeThat)) && $from.parent.type.name === "paragraph";
      if (isStartSlash || isMidlineSlash) {
        try {
          const coords = editor.view.coordsAtPos(from);
          const box = containerRef.current?.getBoundingClientRect();
          setSlashCoords({
            top: coords.bottom - (box?.top || 0) + 8,
            left: coords.left - (box?.left || 0),
          });
          setSlashOpen(true);
        } catch (e) { /* ignore */ }
      } else {
        setSlashOpen(false);
      }
    };
    editor.on("selectionUpdate", handle);
    editor.on("update", handle);
    return () => {
      editor.off("selectionUpdate", handle);
      editor.off("update", handle);
    };
  }, [editor]);

  const runSlash = (action) => {
    if (!editor) return;
    // Delete the "/" character immediately before the cursor (or the whole "/" paragraph in start mode)
    const { from } = editor.state.selection;
    editor.chain().focus().deleteRange({ from: from - 1, to: from }).run();
    setSlashOpen(false);
    // Defer slightly so the deleteRange transaction commits before the action runs
    setTimeout(() => action(), 0);
  };

  if (!editor) return <div className="font-serif text-sm text-muted-ink">Loading editor.</div>;

  return (
    <div className="relative" ref={containerRef} data-testid="rich-text-editor">
      <Toolbar editor={editor} onLink={promptLink} onYouTube={promptYouTube} onUpload={openFile} uploadKind={uploadKind} />
      <input
        ref={fileInputRef}
        type="file"
        className="hidden"
        onChange={onFile}
        data-testid="rich-editor-file"
      />
      <div className="border hairline rounded-sm p-4 bg-cream">
        <EditorContent editor={editor} />
        {!editor.getText() && placeholder && (
          <p className="pointer-events-none font-serif italic text-muted-ink/60 -mt-[1.6rem] sm:-mt-[1.8rem] pl-0">
            {placeholder}
          </p>
        )}
      </div>

      <BubbleMenu
        editor={editor}
        shouldShow={({ editor, from, to }) => {
          // Only show when there is a non-collapsed text selection inside the editor
          if (!editor.isEditable || from === to) return false;
          return editor.isFocused;
        }}
        options={{ placement: "top" }}
      >
        <div data-testid="rich-bubble-menu" className="flex items-center gap-1 border hairline rounded-sm bg-cream shadow-md px-1 py-1">
          {[
            { k: "bold", l: "B", className: "font-semibold", on: editor.isActive("bold"), run: () => editor.chain().focus().toggleBold().run() },
            { k: "italic", l: "I", className: "italic", on: editor.isActive("italic"), run: () => editor.chain().focus().toggleItalic().run() },
            { k: "link", l: "Link", className: "", on: editor.isActive("link"), run: promptLink },
          ].map((it) => (
            <button
              key={it.k}
              type="button"
              data-testid={`bubble-${it.k}`}
              onMouseDown={(e) => { e.preventDefault(); it.run(); }}
              className={`${it.className} px-2 py-1 font-sans text-xs uppercase tracking-wider rounded-sm transition-colors ${it.on ? "bg-gold text-cream" : "text-muted-ink hover:text-gold"}`}
            >
              {it.l}
            </button>
          ))}
        </div>
      </BubbleMenu>

      {slashOpen && (
        <div
          data-testid="rich-slash-menu"
          className="absolute z-30 border hairline rounded-sm bg-cream shadow-md min-w-[200px]"
          style={{ top: slashCoords.top, left: slashCoords.left }}
        >
          {[
            { k: "h1", l: "Heading 1", run: () => editor.chain().focus().toggleHeading({ level: 1 }).run() },
            { k: "h2", l: "Heading 2", run: () => editor.chain().focus().toggleHeading({ level: 2 }).run() },
            { k: "quote", l: "Quote", run: () => editor.chain().focus().toggleBlockquote().run() },
            { k: "ul", l: "Bullet list", run: () => editor.chain().focus().toggleBulletList().run() },
            { k: "ol", l: "Numbered list", run: () => editor.chain().focus().toggleOrderedList().run() },
            { k: "image", l: "Image", run: () => openFile("image") },
            { k: "video", l: "Video", run: () => openFile("video") },
            { k: "audio", l: "Audio", run: () => openFile("audio") },
            { k: "yt", l: "YouTube / Vimeo", run: promptYouTube },
            { k: "hr", l: "Divider", run: () => editor.chain().focus().setHorizontalRule().run() },
          ].map((item) => (
            <button
              key={item.k}
              type="button"
              data-testid={`slash-${item.k}`}
              onMouseDown={(e) => { e.preventDefault(); runSlash(item.run); }}
              className="block w-full text-left px-3 py-1.5 font-sans text-sm ink hover:bg-[#F5EDD6] transition-colors"
            >
              {item.l}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function Toolbar({ editor, onLink, onYouTube, onUpload, uploadKind }) {
  if (!editor) return null;
  const btn = "px-2 py-1 font-sans text-xs uppercase tracking-wider font-semibold rounded-sm transition-colors";
  const active = "bg-gold text-cream";
  const idle = "text-muted-ink hover:text-gold";
  const items = [
    { k: "bold", l: "Bold", on: editor.isActive("bold"), run: () => editor.chain().focus().toggleBold().run() },
    { k: "italic", l: "Italic", on: editor.isActive("italic"), run: () => editor.chain().focus().toggleItalic().run() },
    { k: "h1", l: "H1", on: editor.isActive("heading", { level: 1 }), run: () => editor.chain().focus().toggleHeading({ level: 1 }).run() },
    { k: "h2", l: "H2", on: editor.isActive("heading", { level: 2 }), run: () => editor.chain().focus().toggleHeading({ level: 2 }).run() },
    { k: "quote", l: "Quote", on: editor.isActive("blockquote"), run: () => editor.chain().focus().toggleBlockquote().run() },
    { k: "ul", l: "List", on: editor.isActive("bulletList"), run: () => editor.chain().focus().toggleBulletList().run() },
    { k: "ol", l: "1. List", on: editor.isActive("orderedList"), run: () => editor.chain().focus().toggleOrderedList().run() },
    { k: "link", l: "Link", on: editor.isActive("link"), run: onLink },
  ];
  return (
    <div className="flex items-center gap-1 flex-wrap mb-2 border-b hairline pb-2" data-testid="rich-toolbar">
      {items.map((it) => (
        <button
          key={it.k}
          type="button"
          data-testid={`rt-${it.k}`}
          onMouseDown={(e) => { e.preventDefault(); it.run(); }}
          className={`${btn} ${it.on ? active : idle}`}
        >
          {it.l}
        </button>
      ))}
      <span className="w-px h-4 bg-gold-mid mx-1" />
      <button type="button" data-testid="rt-image" onMouseDown={(e) => { e.preventDefault(); onUpload("image"); }} className={`${btn} ${idle}`}>{uploadKind === "image" ? "Uploading..." : "Image"}</button>
      <button type="button" data-testid="rt-video" onMouseDown={(e) => { e.preventDefault(); onUpload("video"); }} className={`${btn} ${idle}`}>{uploadKind === "video" ? "Uploading..." : "Video"}</button>
      <button type="button" data-testid="rt-audio" onMouseDown={(e) => { e.preventDefault(); onUpload("audio"); }} className={`${btn} ${idle}`}>{uploadKind === "audio" ? "Uploading..." : "Audio"}</button>
      <button type="button" data-testid="rt-youtube" onMouseDown={(e) => { e.preventDefault(); onYouTube(); }} className={`${btn} ${idle}`}>YouTube</button>
    </div>
  );
}
