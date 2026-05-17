import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import api, { API } from "@/lib/api";
import PostItem from "@/components/PostItem";
import PageMeta from "@/components/PageMeta";
import EntitlementBadge from "@/components/EntitlementBadge";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

function fmtEssay(iso) {
  if (!iso) return "";
  try {
    return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(new Date(iso));
  } catch { return ""; }
}

export default function Profile() {
  const { id } = useParams();
  const { user } = useAuth();
  const [profile, setProfile] = useState(null);
  const [posts, setPosts] = useState([]);
  const [essays, setEssays] = useState([]);
  const [rel, setRel] = useState(null);
  const [notFound, setNotFound] = useState(false);
  const [following, setFollowing] = useState([]);
  const [busy, setBusy] = useState(false);

  const isSelf = !id || (user && id === user.user_id);
  const targetId = isSelf ? user?.user_id : id;

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const url = isSelf ? "/profile" : `/profile/${id}`;
        const r = await api.get(url);
        if (cancelled) return;
        if (r.data && r.data.user_id) {
          setProfile(r.data);
          const pr = await api.get(`/posts/by-user/${r.data.user_id}`);
          if (!cancelled) setPosts(pr.data.items || []);
          const ess = await api.get(`/profile/${r.data.user_id}/essays`);
          if (!cancelled) setEssays(ess.data.items || []);
          if (user) {
            const relRes = await api.get(`/users/${r.data.user_id}/relationship`);
            if (!cancelled) setRel(relRes.data);
            if (isSelf) {
              const fr = await api.get("/me/following");
              if (!cancelled) setFollowing(fr.data.items || []);
            }
          }
        } else {
          setNotFound(true);
        }
      } catch (e) {
        if (!cancelled) setNotFound(true);
      }
    })();
    return () => { cancelled = true; };
  }, [id, isSelf, user]);

  const toggleFollow = async () => {
    if (!rel || isSelf) return;
    setBusy(true);
    try {
      if (rel.is_following) {
        await api.delete(`/users/${targetId}/follow`);
        setRel({ ...rel, is_following: false });
        toast.success("Unfollowed");
      } else {
        await api.post(`/users/${targetId}/follow`);
        setRel({ ...rel, is_following: true });
        toast.success("Following");
      }
    } catch (e) {
      toast.error("Could not update follow");
    } finally {
      setBusy(false);
    }
  };

  if (notFound) {
    return (
      <div className="container-prose py-24 text-center">
        <p className="uppercase-label mb-3">Not found</p>
        <p className="font-serif text-base ink/80">No profile to show.</p>
      </div>
    );
  }
  if (!profile) {
    return <div className="container-prose py-24 text-center font-serif text-muted-ink">Loading.</div>;
  }

  const avatarUrl = profile.avatar_path ? `${API}/uploads/file/${profile.avatar_path}` : null;

  return (
    <div className="container-prose py-16">
      <PageMeta
        title={profile.name || "Member"}
        description={profile.bio || `${profile.name}'s page on The Housing News.`}
        image={avatarUrl}
        kind="article"
        author={profile.name}
      />
      <section className="flex flex-col sm:flex-row gap-8 mb-12">
        <div className="w-24 h-24 rounded-full bg-[#F5EDD6] border hairline overflow-hidden flex items-center justify-center shrink-0">
          {avatarUrl ? <img src={avatarUrl} alt="" className="w-full h-full object-cover" /> : (
            <span className="font-display text-3xl text-gold">{(profile.name || "M")[0]}</span>
          )}
        </div>
        <div className="flex-1 min-w-0">
          <p className="uppercase-label mb-2">{profile.market}</p>
          <h1 className="font-display font-semibold text-3xl ink mb-2 flex items-center gap-3 flex-wrap">
            {profile.name}
            {profile.linkedin_url && (
              <a
                href={profile.linkedin_url}
                target="_blank"
                rel="noopener noreferrer"
                data-testid="profile-linkedin-link"
                aria-label={`${profile.name} on LinkedIn`}
                className="inline-flex items-center justify-center w-7 h-7 rounded-sm bg-[#0A66C2] text-white hover:opacity-80 transition-opacity"
                title="View on LinkedIn"
              >
                <svg viewBox="0 0 24 24" className="w-4 h-4" fill="currentColor" aria-hidden="true">
                  <path d="M20.5 2h-17A1.5 1.5 0 0 0 2 3.5v17A1.5 1.5 0 0 0 3.5 22h17a1.5 1.5 0 0 0 1.5-1.5v-17A1.5 1.5 0 0 0 20.5 2zM8 19H5v-9h3zM6.5 8.25A1.75 1.75 0 1 1 8.25 6.5 1.75 1.75 0 0 1 6.5 8.25zM19 19h-3v-4.74c0-1.42-.6-1.93-1.38-1.93A1.74 1.74 0 0 0 13 14.19a1 1 0 0 0 0 .19V19h-3v-9h2.9v1.3a3.11 3.11 0 0 1 2.7-1.4c1.55 0 3.36.86 3.36 3.66z"/>
                </svg>
              </a>
            )}
          </h1>
          {profile.bio && <p className="prose-serif text-base ink/80 leading-relaxed mb-4 max-w-prose">{profile.bio}</p>}

          {isSelf && <EntitlementBadge />}

          <div className="flex items-center gap-4 mt-3">
            {isSelf ? (
              <>
                <Link to="/onboarding" data-testid="profile-edit-link" className="font-sans text-sm font-medium ink hover:text-gold transition-colors underline underline-offset-4 decoration-gold-mid">
                  Edit profile
                </Link>
                <Link to="/settings" data-testid="profile-settings-link" className="font-sans text-sm font-medium ink hover:text-gold transition-colors underline underline-offset-4 decoration-gold-mid">
                  Inbox preferences
                </Link>
              </>
            ) : (
              rel && (
                <button
                  data-testid="profile-follow-btn"
                  onClick={toggleFollow}
                  disabled={busy}
                  className={`font-sans font-semibold text-sm px-5 py-2 rounded-sm transition-opacity disabled:opacity-50 ${rel.is_following ? "border border-gold text-gold hover:bg-gold-mid" : "bg-gold text-cream hover:opacity-90"}`}
                >
                  {rel.is_following ? "Following" : "Follow"}
                </button>
              )
            )}
          </div>
        </div>
      </section>

      <section className="border-t hairline pt-10 mb-12" data-testid="profile-objectives">
        <p className="uppercase-label mb-4">Public objectives <span className="text-muted-ink"> &middot; v{profile.objectives_version || 1}</span></p>
        <ol className="space-y-3">
          {(profile.objectives || []).map((o, i) => (
            <li key={i} className="flex gap-4">
              <div className="font-display text-lg text-gold w-6 shrink-0">{i + 1}</div>
              <div className="prose-serif text-base ink/90 leading-relaxed">{o}</div>
            </li>
          ))}
        </ol>
      </section>

      <CareerBlock data={profile.linkedin_data} linkedinUrl={profile.linkedin_url} />

      {isSelf && following.length > 0 && (
        <section className="border-t hairline pt-10 mb-12" data-testid="profile-following">
          <p className="uppercase-label mb-4">You follow</p>
          <ul className="grid sm:grid-cols-2 gap-x-6">
            {following.map((m) => (
              <li key={m.user_id} className="py-2">
                <Link to={`/profile/${m.user_id}`} className="font-sans text-sm font-medium ink hover:text-gold transition-colors">
                  {m.name} <span className="text-muted-ink">{m.market ? `· ${m.market}` : ""}</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="border-t hairline pt-10">
        <p className="uppercase-label mb-6">Recent posts</p>
        {posts.length === 0 ? (
          <p className="font-serif text-base text-muted-ink">No posts yet.</p>
        ) : (
          posts.filter((p) => (p.kind || "post") === "post").map((p) => <PostItem key={p.post_id} post={p} />)
        )}
      </section>

      {essays.length > 0 && (
        <section className="border-t hairline pt-10 mt-12" data-testid="profile-essays-archive">
          <p className="uppercase-label mb-6">Essays</p>
          <ul className="divide-y divide-[#E8D4A0] border-t border-b hairline">
            {essays.map((e) => (
              <li key={e.post_id} data-testid={`archive-essay-${e.post_id}`} className="py-5">
                <Link to={`/essays/${e.post_id}`} className="block group">
                  <div className="flex items-baseline gap-3">
                    <h3 className="font-display font-semibold text-lg ink group-hover:text-gold transition-colors flex-1">{e.title}</h3>
                    <span className="font-sans text-xs text-muted-ink whitespace-nowrap">{fmtEssay(e.release_at || e.created_at)}</span>
                  </div>
                  {e.subtitle && <p className="font-serif italic text-sm text-[#2C2410]/70 mt-1">{e.subtitle}</p>}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

// ── Career block ───────────────────────────────────────────────────────────
// Renders cached LinkedIn experiences + education from `profile.linkedin_data`
// (populated by the EnrichLayer import / Re-sync flow). Hidden gracefully when
// no data is on file. Headline + summary surface at the top, then up to 5
// experiences and 3 schools.
function CareerBlock({ data, linkedinUrl }) {
  if (!data) return null;
  const experiences = Array.isArray(data.experiences) ? data.experiences.filter((e) => e.company || e.title) : [];
  const education = Array.isArray(data.education) ? data.education.filter((e) => e.school) : [];
  const headline = data.headline || data.occupation || "";
  const summary = data.summary || "";

  if (!headline && !summary && experiences.length === 0 && education.length === 0) return null;

  const fmtYears = (s, e) => {
    if (!s && !e) return null;
    if (s && e) return `${s} – ${e}`;
    if (s) return `${s} – Present`;
    return `${e}`;
  };

  return (
    <section className="border-t hairline pt-10 mb-12" data-testid="profile-career">
      <p className="uppercase-label mb-4">Career</p>

      {headline && (
        <p className="font-display font-semibold text-lg ink mb-2" data-testid="career-headline">
          {headline}
        </p>
      )}
      {summary && (
        <p className="prose-serif text-[15px] ink/80 leading-relaxed max-w-prose mb-8 whitespace-pre-line" data-testid="career-summary">
          {summary.length > 600 ? `${summary.slice(0, 600)}…` : summary}
        </p>
      )}

      {experiences.length > 0 && (
        <div className="mb-8" data-testid="career-experiences">
          <p className="font-sans text-[11px] uppercase tracking-[0.18em] font-semibold text-gold mb-4">Experience</p>
          <ul className="divide-y divide-[#E8D4A0] border-t border-b hairline">
            {experiences.slice(0, 5).map((e, i) => {
              const years = fmtYears(e.starts_at, e.ends_at);
              return (
                <li key={i} data-testid={`career-experience-${i}`} className="py-4 flex items-baseline gap-3">
                  <div className="flex-1 min-w-0">
                    {e.title && <div className="font-display font-semibold text-base ink">{e.title}</div>}
                    {e.company && (
                      <div className="font-serif text-sm ink/80 mt-0.5">
                        {e.company}
                        {e.location ? <span className="text-muted-ink"> · {e.location}</span> : null}
                      </div>
                    )}
                  </div>
                  {years && (
                    <span className="font-sans text-xs text-muted-ink whitespace-nowrap font-mono">{years}</span>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {education.length > 0 && (
        <div data-testid="career-education">
          <p className="font-sans text-[11px] uppercase tracking-[0.18em] font-semibold text-gold mb-4">Education</p>
          <ul className="divide-y divide-[#E8D4A0] border-t border-b hairline">
            {education.slice(0, 3).map((e, i) => {
              const years = fmtYears(e.starts_at, e.ends_at);
              const detail = [e.degree, e.field].filter(Boolean).join(" · ");
              return (
                <li key={i} data-testid={`career-education-${i}`} className="py-4 flex items-baseline gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="font-display font-semibold text-base ink">{e.school}</div>
                    {detail && <div className="font-serif text-sm ink/80 mt-0.5">{detail}</div>}
                  </div>
                  {years && (
                    <span className="font-sans text-xs text-muted-ink whitespace-nowrap font-mono">{years}</span>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {linkedinUrl && (
        <p className="font-sans text-[11px] uppercase tracking-[0.18em] text-muted-ink mt-5">
          Sourced from{" "}
          <a
            href={linkedinUrl}
            target="_blank"
            rel="noopener noreferrer"
            data-testid="career-linkedin-source"
            className="text-gold hover:opacity-80 transition-opacity underline underline-offset-2"
          >
            LinkedIn
          </a>
          .
        </p>
      )}
    </section>
  );
}
