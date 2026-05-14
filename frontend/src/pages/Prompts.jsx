import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

function formatRange(ws, we) {
  try {
    const opts = { month: "short", day: "numeric", timeZone: "America/Chicago" };
    const a = new Intl.DateTimeFormat("en-US", opts).format(new Date(ws));
    const b = new Intl.DateTimeFormat("en-US", opts).format(new Date(we));
    return `${a} – ${b}`;
  } catch { return ""; }
}

export default function Prompts() {
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [suggestion, setSuggestion] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api.get("/prompts").then((r) => setItems(r.data.items || [])).finally(() => setLoading(false));
  }, []);

  const submitSuggestion = async (e) => {
    e.preventDefault();
    if (suggestion.trim().length < 10) { toast.error("Tell us a bit more, ten characters at least"); return; }
    setSubmitting(true);
    try {
      await api.post("/prompts/suggestions", { text: suggestion.trim() });
      toast.success("Suggestion sent to the editors");
      setSuggestion("");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not send");
    } finally { setSubmitting(false); }
  };

  const current = items.find((p) => p.status === "active");
  const past = items.filter((p) => p.status === "past");

  return (
    <div className="container-prose py-12" data-testid="prompts-page">
      <p className="uppercase-label mb-3">Subjects</p>
      <h1 className="font-display font-semibold text-4xl ink leading-tight">Subject of the week.</h1>
      <p className="font-serif text-base text-muted-ink mt-3 max-w-2xl">
        A small writing prompt every Monday morning. Take it or leave it. The point is to start.
      </p>

      {loading ? (
        <div className="font-serif text-base text-muted-ink py-12 text-center">Loading.</div>
      ) : (
        <>
          {current && (
            <section className="mt-10" data-testid="prompts-current">
              <div className="border-2 border-gold rounded-sm p-8 bg-cream">
                <div className="flex items-center gap-2 mb-3">
                  <span className="font-sans text-[10px] uppercase tracking-[0.18em] font-semibold text-gold">This week</span>
                  <span className="font-sans text-xs text-muted-ink">. {formatRange(current.week_start, current.week_end)}</span>
                </div>
                <Link to={`/prompts/${current.prompt_id}`} className="group">
                  <h2 className="font-display font-semibold text-2xl sm:text-3xl ink group-hover:text-gold transition-colors leading-tight mb-3">
                    {current.title}
                  </h2>
                </Link>
                {current.body && (
                  <p className="prose-serif text-base ink/85 leading-relaxed mb-4">{current.body}</p>
                )}
                <div className="flex items-center gap-3 flex-wrap">
                  <Link to={`/prompts/${current.prompt_id}`} className="font-sans text-xs uppercase tracking-wider font-semibold text-gold hover:opacity-80 transition-opacity">
                    {current.response_count || 0} {current.response_count === 1 ? "response" : "responses"} →
                  </Link>
                  {user && user.status === "approved" && (
                    <Link to="/write" className="font-sans text-xs uppercase tracking-wider font-semibold text-muted-ink hover:text-gold transition-colors">
                      Write something →
                    </Link>
                  )}
                </div>
              </div>
            </section>
          )}

          {user && user.status === "approved" && (
            <section className="mt-12" data-testid="prompts-suggest">
              <p className="uppercase-label mb-3">Suggest a subject</p>
              <form onSubmit={submitSuggestion} className="flex items-start gap-3">
                <textarea
                  data-testid="prompts-suggest-input"
                  value={suggestion}
                  onChange={(e) => setSuggestion(e.target.value)}
                  placeholder="A short idea, one line. The editors read them all."
                  maxLength={300}
                  className="flex-1 bg-cream border hairline rounded-sm p-3 font-serif text-sm ink focus:outline-none focus:ring-1 focus:ring-gold min-h-[80px]"
                />
                <button
                  data-testid="prompts-suggest-submit"
                  type="submit"
                  disabled={submitting}
                  className="bg-gold text-cream font-sans font-semibold text-sm px-5 py-2.5 rounded-sm hover:opacity-90 transition-opacity disabled:opacity-50"
                >
                  {submitting ? "Sending..." : "Send"}
                </button>
              </form>
            </section>
          )}

          <section className="mt-16" data-testid="prompts-archive">
            <p className="uppercase-label mb-4">Past subjects</p>
            {past.length === 0 ? (
              <p className="font-serif text-base text-muted-ink italic">No archive yet.</p>
            ) : (
              <div className="border hairline rounded-sm divide-y divide-[#E8D4A0]">
                {past.map((p) => (
                  <Link key={p.prompt_id} to={`/prompts/${p.prompt_id}`} data-testid={`prompts-past-${p.prompt_id}`} className="block px-5 py-4 hover:bg-[#F5EDD6]/40 transition-colors group">
                    <h3 className="font-display font-semibold text-base ink group-hover:text-gold transition-colors mb-1">{p.title}</h3>
                    <div className="font-sans text-xs text-muted-ink">
                      {formatRange(p.week_start, p.week_end)} . {p.response_count || 0} {p.response_count === 1 ? "response" : "responses"}
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
