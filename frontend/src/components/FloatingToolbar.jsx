import React, { useEffect, useRef, useState } from "react";

/**
 * Substack-style selection toolbar.
 *
 * Watches the document selection inside `editorRef` and renders a small dark
 * pill above the highlighted range with formatting actions. For now we wrap
 * the selection in markdown delimiters via the standard `setRangeText` API
 * so the toolbar works against the raw `<textarea>` editor without needing
 * a rich-text engine. The visual rich-text editor handles its own toolbar.
 *
 * Props
 *  - editorRef: ref pointing at a <textarea> element to operate on.
 *  - onChange: (newValue) => void  — called with the textarea's updated value.
 *  - active: bool — when false the toolbar never renders (e.g. visual mode).
 */
export default function FloatingToolbar({ editorRef, onChange, active = true }) {
  const [coords, setCoords] = useState(null);
  const toolbarRef = useRef(null);

  useEffect(() => {
    if (!active) return undefined;
    const el = editorRef.current;
    if (!el) return undefined;

    const recompute = () => {
      // Only show when a non-empty range is selected inside our textarea.
      if (document.activeElement !== el) { setCoords(null); return; }
      const start = el.selectionStart ?? 0;
      const end = el.selectionEnd ?? 0;
      if (start === end) { setCoords(null); return; }
      const rect = el.getBoundingClientRect();
      // Use VIEWPORT coords with position: fixed so the toolbar tracks the
      // selection during scroll without us having to reposition on every
      // scroll event. Sits 44px above the top of the textarea, horizontally
      // centred — textareas don't expose per-char coordinates so we anchor
      // to the editor top, which is close enough to the Substack pattern.
      setCoords({
        top: rect.top - 44,
        left: rect.left + rect.width / 2,
      });
    };
    const clear = () => setCoords(null);
    el.addEventListener("select", recompute);
    el.addEventListener("keyup", recompute);
    el.addEventListener("mouseup", recompute);
    el.addEventListener("blur", (e) => {
      // Keep the toolbar visible if focus moved INTO the toolbar itself.
      if (toolbarRef.current && toolbarRef.current.contains(e.relatedTarget)) return;
      clear();
    });
    window.addEventListener("scroll", recompute, true);
    window.addEventListener("resize", recompute);
    return () => {
      el.removeEventListener("select", recompute);
      el.removeEventListener("keyup", recompute);
      el.removeEventListener("mouseup", recompute);
      window.removeEventListener("scroll", recompute, true);
      window.removeEventListener("resize", recompute);
    };
  }, [editorRef, active]);

  const wrap = (open, close = null) => {
    const el = editorRef.current;
    if (!el) return;
    const start = el.selectionStart ?? 0;
    const end = el.selectionEnd ?? 0;
    if (start === end) return;
    const before = el.value.slice(0, start);
    const sel = el.value.slice(start, end);
    const after = el.value.slice(end);
    const closeStr = close ?? open;
    const next = `${before}${open}${sel}${closeStr}${after}`;
    onChange(next);
    // Restore selection around the formatted text on next tick.
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(start + open.length, end + open.length);
    });
  };

  const prefixLine = (prefix) => {
    const el = editorRef.current;
    if (!el) return;
    const start = el.selectionStart ?? 0;
    const end = el.selectionEnd ?? 0;
    if (start === end) return;
    // Expand selection backwards to the start of the line so the prefix
    // attaches at line-start, which is how markdown headings / quotes work.
    const lineStart = el.value.lastIndexOf("\n", start - 1) + 1;
    const before = el.value.slice(0, lineStart);
    const sel = el.value.slice(lineStart, end);
    const after = el.value.slice(end);
    const next = `${before}${prefix}${sel}${after}`;
    onChange(next);
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(start + prefix.length, end + prefix.length);
    });
  };

  const addLink = () => {
    const url = window.prompt("Link URL");
    if (!url) return;
    const el = editorRef.current;
    if (!el) return;
    const start = el.selectionStart ?? 0;
    const end = el.selectionEnd ?? 0;
    if (start === end) return;
    const sel = el.value.slice(start, end);
    const before = el.value.slice(0, start);
    const after = el.value.slice(end);
    onChange(`${before}[${sel}](${url})${after}`);
  };

  if (!active || !coords) return null;

  const Btn = ({ onClick, label, testid, monospace = false }) => (
    <button
      type="button"
      data-testid={testid}
      onMouseDown={(e) => { e.preventDefault(); onClick(); }}
      className={`px-2 py-1 rounded hover:bg-white/10 transition-colors text-sm ${monospace ? "font-mono" : "font-semibold"}`}
    >
      {label}
    </button>
  );

  return (
    <div
      ref={toolbarRef}
      data-testid="floating-selection-toolbar"
      style={{ position: "fixed", top: coords.top, left: coords.left, transform: "translateX(-50%)" }}
      className="z-50 flex items-center bg-[#1D2D44] text-[#FDFAF4] rounded-lg shadow-xl px-2 py-1 gap-1"
    >
      <Btn testid="ft-bold" label="B" onClick={() => wrap("**")} />
      <Btn testid="ft-italic" label="I" onClick={() => wrap("_")} monospace={false} />
      <span className="w-px h-5 bg-white/20 mx-1" />
      <Btn testid="ft-h2" label="H2" onClick={() => prefixLine("## ")} />
      <Btn testid="ft-quote" label={'""'} onClick={() => prefixLine("> ")} monospace />
      <span className="w-px h-5 bg-white/20 mx-1" />
      <Btn testid="ft-link" label="Link" onClick={addLink} monospace={false} />
    </div>
  );
}
