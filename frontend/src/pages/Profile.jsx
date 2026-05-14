import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import api, { API } from "@/lib/api";
import PostItem from "@/components/PostItem";
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
      <section className="flex flex-col sm:flex-row gap-8 mb-12">
        <div className="w-24 h-24 rounded-full bg-[#F5EDD6] border hairline overflow-hidden flex items-center justify-center shrink-0">
          {avatarUrl ? <img src={avatarUrl} alt="" className="w-full h-full object-cover" /> : (
            <span className="font-display text-3xl text-gold">{(profile.name || "M")[0]}</span>
          )}
        </div>
        <div className="flex-1 min-w-0">
          <p className="uppercase-label mb-2">{profile.market}</p>
          <h1 className="font-display font-semibold text-3xl ink mb-2">{profile.name}</h1>
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
