import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import PostItem from "@/components/PostItem";

export default function PublicFeed() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/posts/public").then((r) => setItems(r.data.items || [])).finally(() => setLoading(false));
  }, []);

  return (
    <div className="container-prose py-16">
      <p className="uppercase-label mb-3">Public feed</p>
      <h1 className="font-display font-semibold text-3xl sm:text-4xl ink mb-3">The last two weeks, in public.</h1>
      <p className="font-serif text-base ink/80 leading-relaxed max-w-prose mb-12">
        A read-only window into the Network. The full feed is for members.
      </p>
      {loading ? (
        <div className="font-serif text-base text-muted-ink py-12 text-center">Loading.</div>
      ) : items.length === 0 ? (
        <div className="border hairline rounded-sm py-16 text-center" data-testid="public-empty">
          <p className="uppercase-label mb-3">Nothing yet</p>
          <p className="font-serif text-base ink/80 max-w-prose mx-auto">
            No posts in the last 14 days. Check back at the next release window.
          </p>
        </div>
      ) : (
        <div>{items.map((p) => <PostItem key={p.post_id} post={p} />)}</div>
      )}
    </div>
  );
}
