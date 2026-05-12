import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import api, { API } from "@/lib/api";
import PostItem from "@/components/PostItem";
import { useAuth } from "@/context/AuthContext";

export default function Profile() {
  const { id } = useParams();
  const { user } = useAuth();
  const [profile, setProfile] = useState(null);
  const [posts, setPosts] = useState([]);
  const [notFound, setNotFound] = useState(false);

  const isSelf = !id || (user && id === user.user_id);

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
        } else {
          setNotFound(true);
        }
      } catch (e) {
        if (!cancelled) setNotFound(true);
      }
    })();
    return () => { cancelled = true; };
  }, [id, isSelf]);

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
          {isSelf && (
            <Link to="/onboarding" data-testid="profile-edit-link" className="font-sans text-sm font-medium ink hover:text-gold transition-colors underline underline-offset-4 decoration-gold-mid">
              Edit profile
            </Link>
          )}
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

      <section className="border-t hairline pt-10">
        <p className="uppercase-label mb-6">Recent posts</p>
        {posts.length === 0 ? (
          <p className="font-serif text-base text-muted-ink">No posts yet.</p>
        ) : (
          posts.map((p) => <PostItem key={p.post_id} post={p} />)
        )}
      </section>
    </div>
  );
}
