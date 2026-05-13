import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import api, { API } from "@/lib/api";

function formatDate(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "America/Chicago" }).format(d);
  } catch { return ""; }
}

export default function PromptDetail() {
  const { id } = useParams();
  const [prompt, setPrompt] = useState(null);
  const [notFound, setNotFound] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setNotFound(false);
    api.get(`/prompts/${id}`)
      .then((r) => { if (!cancelled) setPrompt(r.data); })
      .catch(() => { if (!cancelled) setNotFound(true); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [id]);

  if (loading) return <div className="container-prose py-24 text-center font-serif text-muted-ink">Loading.</div>;
  if (notFound || !prompt) {
    return (
      <div className="container-prose py-24 text-center">
        <p className="uppercase-label mb-3">Not found</p>
        <p className="font-serif text-base ink/80">No subject to show.</p>
      </div>
    );
  }

  return (
    <div className="container-prose py-12" data-testid="prompt-detail">
      <Link to="/prompts" className="font-sans text-xs uppercase tracking-wider text-muted-ink hover:text-gold transition-colors mb-4 inline-block">
        ← All subjects
      </Link>
      <p className="uppercase-label mb-3">
        {prompt.status === "active" ? "This week" : "Past subject"} . {formatDate(prompt.week_start)}
      </p>
      <h1 className="font-display font-semibold text-3xl sm:text-4xl ink leading-tight mb-4">{prompt.title}</h1>
      {prompt.body && (
        <p className="prose-serif text-base sm:text-lg ink/85 leading-relaxed mb-10">{prompt.body}</p>
      )}

      <section data-testid="prompt-responses">
        <p className="uppercase-label mb-4">Responses ({prompt.response_count || 0})</p>
        {(!prompt.responses || prompt.responses.length === 0) ? (
          <p className="font-serif text-base text-muted-ink italic">No responses yet. Be the first.</p>
        ) : (
          <div className="space-y-4">
            {prompt.responses.map((p) => {
              const isEssay = p.kind === "essay";
              const author = p.author || {};
              const avatar = author.avatar_path ? `${API}/uploads/file/${author.avatar_path}` : null;
              const href = isEssay ? `/essays/${p.post_id}` : `/feed`;
              return (
                <Link key={p.post_id} to={href} data-testid={`prompt-response-${p.post_id}`} className="block border hairline rounded-sm p-5 bg-cream hover:border-gold transition-colors group">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="font-sans text-[10px] uppercase tracking-wider font-semibold text-gold">{isEssay ? "Essay" : "Post"}</span>
                    <span className="font-sans text-xs text-muted-ink">. {formatDate(p.release_at)}</span>
                  </div>
                  {isEssay ? (
                    <>
                      <h3 className="font-display font-semibold text-lg ink group-hover:text-gold transition-colors mb-1">{p.title}</h3>
                      {p.subtitle && <p className="font-serif italic text-sm text-[#2C2410]/75 line-clamp-2">{p.subtitle}</p>}
                    </>
                  ) : null}
                  <div className="flex items-center gap-2 mt-3">
                    <div className="w-5 h-5 rounded-full bg-[#F5EDD6] border hairline overflow-hidden flex items-center justify-center">
                      {avatar ? <img src={avatar} alt="" className="w-full h-full object-cover" /> : <span className="font-display text-[9px] text-gold">{(author.name || "M")[0]}</span>}
                    </div>
                    <span className="font-sans text-xs ink font-semibold">{author.name}</span>
                    {author.market && <span className="font-sans text-xs text-muted-ink">. {author.market}</span>}
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
