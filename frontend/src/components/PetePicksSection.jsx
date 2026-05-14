import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import PostItem from "@/components/PostItem";

export default function PetePicksSection({ compact = false, max = 3 }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get(`/posts/picks?limit=${max}`).then((r) => setItems(r.data.items || [])).finally(() => setLoading(false));
  }, [max]);

  if (loading) return null;
  if (items.length === 0) return null;

  return (
    <section className="border hairline rounded-sm p-6 sm:p-8 bg-[#F5EDD6]/40" data-testid="pete-picks-section">
      <div className="flex items-center gap-3 mb-6">
        <span className="font-sans text-[11px] uppercase tracking-[0.18em] font-semibold text-gold">Staff picks</span>
        <span className="h-px flex-1 bg-gold-mid" />
      </div>
      <div className="space-y-2 divide-y divide-[#E8D4A0]">
        {items.map((p) => <PostItem key={p.post_id} post={p} showReplies={false} compact={compact} />)}
      </div>
    </section>
  );
}
