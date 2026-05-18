import React, { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import RegionPicker from "@/components/RegionPicker";
import { resetOnboarding } from "@/components/OnboardingChecklist";
import { toast } from "sonner";

export default function Settings() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const [prefs, setPrefs] = useState({ am: true, pm: true, brief_morning: true, brief_evening: true });
  const [fetching, setFetching] = useState(true);
  const [saving, setSaving] = useState(false);
  const [invites, setInvites] = useState(null);
  const [genBusy, setGenBusy] = useState(false);
  const [pats, setPats] = useState([]);
  const [newPatName, setNewPatName] = useState("");
  const [newPatScopes, setNewPatScopes] = useState([]); // empty = full access
  const [newPatBusy, setNewPatBusy] = useState(false);
  const [revealedToken, setRevealedToken] = useState(null);
  const [scopeCatalog, setScopeCatalog] = useState([]);
  const [profile, setProfile] = useState(null);
  const [linkedinBusy, setLinkedinBusy] = useState(false);

  useEffect(() => {
    if (loading) return;
    if (!user) { navigate("/", { replace: true }); return; }
    if (user.status !== "approved") { navigate("/feed", { replace: true }); return; }
    Promise.all([
      api.get("/me/digest-prefs").then((r) => setPrefs({
        am: r.data.am !== false,
        pm: r.data.pm !== false,
        brief_morning: r.data.brief_morning !== false,
        brief_evening: r.data.brief_evening !== false,
      })),
      api.get("/me/invites").then((r) => setInvites(r.data)).catch(() => setInvites(null)),
      api.get("/pats").then((r) => setPats(r.data.items || [])).catch(() => setPats([])),
      api.get("/pats/scopes").then((r) => setScopeCatalog(r.data.items || [])).catch(() => setScopeCatalog([])),
      api.get(`/profile/${user.user_id}`).then((r) => setProfile(r.data)).catch(() => setProfile(null)),
    ]).finally(() => setFetching(false));
  }, [user, loading, navigate]);

  const resyncLinkedin = async () => {
    setLinkedinBusy(true);
    try {
      const r = await api.post("/profile/linkedin-import", { linkedin_url: profile?.linkedin_url || "" });
      // Refresh the cached profile so the synced_at timestamp updates
      const fresh = await api.get(`/profile/${user.user_id}`);
      setProfile(fresh.data);
      toast.success(`Resynced from LinkedIn${r.data?.suggested?.name ? ` — ${r.data.suggested.name}` : ""}`);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not resync");
    } finally { setLinkedinBusy(false); }
  };

  const save = async (next) => {
    setSaving(true);
    try {
      await api.put("/me/digest-prefs", next);
      setPrefs(next);
      toast.success("Saved");
    } catch (e) {
      toast.error("Could not save");
    } finally { setSaving(false); }
  };

  const generate = async () => {
    setGenBusy(true);
    try {
      await api.post("/me/invites");
      const r = await api.get("/me/invites");
      setInvites(r.data);
      toast.success("Code generated");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not generate");
    } finally { setGenBusy(false); }
  };

  const copy = (code) => {
    navigator.clipboard.writeText(code).then(
      () => toast.success("Copied"),
      () => toast.error("Could not copy"),
    );
  };

  const revoke = async (code) => {
    try {
      await api.delete(`/me/invites/${code}`);
      const r = await api.get("/me/invites");
      setInvites(r.data);
      toast.success("Revoked");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not revoke");
    }
  };

  const createPat = async (e) => {
    e.preventDefault();
    if (!newPatName.trim()) return;
    setNewPatBusy(true);
    try {
      const r = await api.post("/pats", { name: newPatName.trim(), scopes: newPatScopes });
      setRevealedToken(r.data.token);
      setNewPatName("");
      setNewPatScopes([]);
      const list = await api.get("/pats");
      setPats(list.data.items || []);
      toast.success("Access token created. Copy it now — you won't see it again.");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not create token");
    } finally { setNewPatBusy(false); }
  };

  const toggleScope = (key) => {
    setNewPatScopes((curr) => curr.includes(key) ? curr.filter((s) => s !== key) : [...curr, key]);
  };

  const revokePat = async (patId) => {
    if (!window.confirm("Revoke this access token? Any integration using it will stop working.")) return;
    try {
      await api.delete(`/pats/${patId}`);
      const list = await api.get("/pats");
      setPats(list.data.items || []);
      toast.success("Revoked");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not revoke");
    }
  };

  const copyToken = (t) => {
    navigator.clipboard.writeText(t).then(
      () => toast.success("Copied"),
      () => toast.error("Copy failed"),
    );
  };

  return (
    <div className="container-prose py-16">
      <p className="uppercase-label mb-3">Settings</p>
      <h1 className="font-display font-semibold text-3xl ink mb-2">Inbox preferences.</h1>
      <p className="prose-serif text-base ink/80 leading-relaxed max-w-prose mb-10">
        Two digest emails a day, after each release window. Turn off either one. You can turn them back on whenever.
      </p>

      {fetching ? (
        <div className="font-serif text-base text-muted-ink">Loading.</div>
      ) : (
        <>
          <p className="font-sans text-[11px] uppercase tracking-[0.18em] font-semibold text-gold mb-3">Member-post digests</p>
          <div className="border hairline rounded-sm divide-y divide-[#E8D4A0]">
            <ToggleRow label="Morning digest" hint="Sent after the 8:30am Chicago release." checked={prefs.am} disabled={saving} onChange={(v) => save({ ...prefs, am: v })} testid="toggle-am" />
            <ToggleRow label="Evening digest" hint="Sent after the 5:30pm Chicago release." checked={prefs.pm} disabled={saving} onChange={(v) => save({ ...prefs, pm: v })} testid="toggle-pm" />
          </div>
          <p className="font-sans text-[11px] uppercase tracking-[0.18em] font-semibold text-gold mt-10 mb-3">Daily Brief (housing news)</p>
          <div className="border hairline rounded-sm divide-y divide-[#E8D4A0]">
            <ToggleRow label="Morning Brief" hint="7:30am Chicago — top 8 publisher articles + 1 podcast pick." checked={prefs.brief_morning !== false} disabled={saving} onChange={(v) => save({ ...prefs, brief_morning: v })} testid="toggle-brief-am" />
            <ToggleRow label="Evening Brief" hint="5:30pm Chicago — top 8 articles + 24h trending topics." checked={prefs.brief_evening !== false} disabled={saving} onChange={(v) => save({ ...prefs, brief_evening: v })} testid="toggle-brief-pm" />
          </div>
        </>
      )}

      {invites && (
        <section id="regions" className="mt-16" data-testid="regions-section">
          <p className="uppercase-label mb-3">Your regions</p>
          <h2 className="font-display font-semibold text-2xl ink mb-2">Personalise your feed.</h2>
          <p className="prose-serif text-base ink/80 leading-relaxed max-w-prose mb-6">
            Pick the cities, metros, states, or regions you care about. We'll
            filter your feed to posts our editors (or Claude) tagged with any
            of these. Leave it empty to see everything — that's the default.
          </p>
          <RegionPicker />
        </section>
      )}

      <section className="mt-16" data-testid="onboarding-section">
        <p className="uppercase-label mb-3">Tour</p>
        <h2 className="font-display font-semibold text-2xl ink mb-2">Show me around again.</h2>
        <p className="prose-serif text-base ink/80 leading-relaxed max-w-prose mb-4">
          Reset the "Getting started" checklist on your feed.
        </p>
        <button
          type="button"
          data-testid="reset-onboarding-btn"
          onClick={() => { resetOnboarding(); toast.success("Checklist reset — head back to your feed."); }}
          className="font-sans text-xs uppercase tracking-wider font-semibold border hairline px-4 py-2 rounded-sm hover:bg-gold hover:text-cream hover:border-gold transition-colors"
        >
          Reset checklist
        </button>
      </section>

      {invites && (
        <section className="mt-16" data-testid="linkedin-section">
          <p className="uppercase-label mb-3">LinkedIn</p>
          <h2 className="font-display font-semibold text-2xl ink mb-2">Career profile.</h2>
          <p className="prose-serif text-base ink/80 leading-relaxed max-w-prose mb-6">
            We pulled your headline, location, work history, and education from LinkedIn when you joined. Re-sync if your role or location has changed and you want the network to see it.
          </p>

          <div className="border hairline rounded-sm bg-cream p-5 flex items-center justify-between gap-4 flex-wrap" data-testid="linkedin-card">
            <div className="min-w-0">
              {profile?.linkedin_url ? (
                <>
                  <div className="font-sans text-xs uppercase tracking-wider text-muted-ink font-semibold">Connected</div>
                  <a
                    href={profile.linkedin_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-display font-semibold text-base ink mt-1 hover:text-gold transition-colors break-all"
                    data-testid="linkedin-url"
                  >
                    {profile.linkedin_url}
                  </a>
                  <div className="font-sans text-xs text-muted-ink mt-1">
                    {profile.linkedin_data?.synced_at
                      ? <>Last synced {new Date(profile.linkedin_data.synced_at).toLocaleString()}</>
                      : <>Not yet synced</>}
                  </div>
                </>
              ) : (
                <>
                  <div className="font-sans text-xs uppercase tracking-wider text-muted-ink font-semibold">Not connected</div>
                  <div className="font-serif text-sm ink/80 mt-1 italic">
                    Add your LinkedIn URL from your profile page first, then re-sync here.
                  </div>
                </>
              )}
            </div>
            <button
              onClick={resyncLinkedin}
              disabled={linkedinBusy || !profile?.linkedin_url}
              data-testid="linkedin-resync-btn"
              className="bg-gold text-cream font-sans font-semibold text-sm px-5 py-2 rounded-sm hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              {linkedinBusy ? "Syncing…" : "Re-sync from LinkedIn"}
            </button>
          </div>
        </section>
      )}

      {invites && (
        <section className="mt-16" data-testid="invites-section">
          <p className="uppercase-label mb-3">Invitations</p>
          <h2 className="font-display font-semibold text-2xl ink mb-2">Bring someone in.</h2>
          <p className="prose-serif text-base ink/80 leading-relaxed max-w-prose mb-6">
            Twenty invite codes, lifetime. Each is one-time-use and expires sixty days after you generate it. We still review every request, but a valid code tells us you vouch for the person. Three approved invites earns you the <strong className="text-gold">Top Connector</strong> badge on your profile and a spot on the public leaderboard.
          </p>

          <div className="border hairline rounded-sm bg-cream p-5 mb-6 grid grid-cols-2 sm:grid-cols-4 gap-4" data-testid="invites-quota">
            <div>
              <div className="font-sans text-[10px] uppercase tracking-wider text-muted-ink font-semibold">Codes left</div>
              <div className="font-display font-semibold text-2xl ink mt-1" data-testid="invites-remaining">
                {invites.remaining}
                <span className="text-muted-ink text-base"> / {invites.lifetime_cap}</span>
              </div>
            </div>
            <div>
              <div className="font-sans text-[10px] uppercase tracking-wider text-muted-ink font-semibold">Sent</div>
              <div className="font-display font-semibold text-2xl ink mt-1">{invites.issued}</div>
            </div>
            <div>
              <div className="font-sans text-[10px] uppercase tracking-wider text-muted-ink font-semibold">Redeemed</div>
              <div className="font-display font-semibold text-2xl ink mt-1">{invites.redeemed}</div>
            </div>
            <div>
              <div className="font-sans text-[10px] uppercase tracking-wider text-gold font-semibold">Approved</div>
              <div className="font-display font-semibold text-2xl ink mt-1" data-testid="invites-approved">
                {invites.approved}
              </div>
              {invites.is_top_connector && (
                <span data-testid="top-connector-badge-mine" className="inline-block mt-2 font-sans text-[9px] uppercase tracking-wider bg-gold text-cream px-1.5 py-0.5 rounded-sm font-semibold">
                  Top Connector
                </span>
              )}
            </div>
          </div>

          <div className="flex items-center justify-between gap-4 flex-wrap mb-6">
            <Link
              to="/referrals"
              data-testid="invites-leaderboard-link"
              className="font-sans text-xs uppercase tracking-[0.18em] font-semibold text-gold hover:text-ink transition-colors"
            >
              View the Top Connectors leaderboard &rarr;
            </Link>
            <button
              data-testid="invites-generate"
              onClick={generate}
              disabled={genBusy || invites.remaining <= 0}
              className="bg-gold text-cream font-sans font-semibold text-sm px-5 py-2 rounded-sm hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              {genBusy ? "Generating..." : "Generate code"}
            </button>
          </div>

          {invites.items.length === 0 ? (
            <p className="font-serif text-sm text-muted-ink italic" data-testid="invites-empty">
              You have not generated any codes yet.
            </p>
          ) : (
            <div className="border hairline rounded-sm divide-y divide-[#E8D4A0]" data-testid="invites-list">
              {invites.items.map((c) => {
                const used = !!c.redeemed_by_user_id;
                const expired = !used && c.expires_at && c.expires_at < new Date().toISOString();
                return (
                  <div key={c.code} data-testid={`invite-${c.code}`} className="px-5 py-4 flex items-center justify-between gap-4 flex-wrap">
                    <div className="min-w-0">
                      <div className="font-display font-semibold text-base ink tracking-widest">{c.code}</div>
                      <div className="font-sans text-xs text-muted-ink mt-0.5">
                        {used ? (
                          <>Redeemed by {c.redeemed_by_email} on {new Date(c.redeemed_at).toLocaleDateString()}</>
                        ) : expired ? (
                          <>Expired</>
                        ) : (
                          <>Expires {new Date(c.expires_at).toLocaleDateString()}</>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {!used && !expired && (
                        <>
                          <button
                            data-testid={`invite-copy-${c.code}`}
                            onClick={() => copy(c.code)}
                            className="font-sans text-xs uppercase tracking-wider font-semibold text-gold hover:opacity-80 transition-opacity px-2"
                          >
                            Copy
                          </button>
                          <button
                            data-testid={`invite-revoke-${c.code}`}
                            onClick={() => revoke(c.code)}
                            className="font-sans text-xs uppercase tracking-wider font-semibold text-muted-ink hover:text-deepred transition-colors px-2"
                          >
                            Revoke
                          </button>
                        </>
                      )}
                      {used && <span className="font-sans text-[10px] uppercase tracking-wide text-gold border border-gold-mid px-1.5 py-0.5 rounded-sm">Used</span>}
                      {expired && <span className="font-sans text-[10px] uppercase tracking-wide text-deepred border border-deepred px-1.5 py-0.5 rounded-sm">Expired</span>}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      )}

      {/* Personal Access Tokens — programmatic posting via Bearer thn_pat_* */}
      <section className="mt-16" data-testid="pats-section">
        <p className="uppercase-label mb-3">Access tokens</p>
        <h2 className="font-display font-semibold text-2xl ink mb-2">Programmatic posting.</h2>
        <p className="prose-serif text-base ink/80 leading-relaxed max-w-prose mb-6">
          Generate a Personal Access Token to post to The Housing News from
          scripts, automations, or LLM agents (e.g. Claude). Each token has the
          same write permissions you do. Treat them like passwords — you can
          only see the value <em>once</em>.
        </p>

        {revealedToken && (
          <div className="border border-gold rounded-sm bg-cream-soft p-5 mb-6" data-testid="pat-just-created">
            <p className="font-sans text-xs uppercase tracking-wider font-semibold text-gold mb-2">
              New token — copy now, it won&apos;t be shown again
            </p>
            <div className="flex items-center gap-3 flex-wrap">
              <code className="font-mono text-sm bg-white border border-gold/40 px-3 py-2 rounded-sm break-all flex-1" data-testid="pat-revealed-token">
                {revealedToken}
              </code>
              <button
                type="button"
                onClick={() => copyToken(revealedToken)}
                data-testid="pat-copy-revealed"
                className="bg-ink text-cream font-sans font-semibold text-sm px-4 py-2 rounded-sm hover:bg-gold transition-colors"
              >
                Copy
              </button>
              <button
                type="button"
                onClick={() => setRevealedToken(null)}
                data-testid="pat-dismiss-revealed"
                className="font-sans text-xs uppercase tracking-wider font-semibold text-muted-ink hover:text-deepred transition-colors"
              >
                I&apos;ve saved it
              </button>
            </div>
          </div>
        )}

        <form onSubmit={createPat} className="border hairline rounded-sm bg-cream p-5 mb-6 space-y-3" data-testid="pat-create-form">
          <div className="flex items-center gap-3 flex-wrap">
            <input
              type="text"
              value={newPatName}
              onChange={(e) => setNewPatName(e.target.value)}
              placeholder="Token name (e.g. Claude Desktop, n8n automation)"
              maxLength={80}
              data-testid="pat-name-input"
              className="flex-1 min-w-[200px] border hairline bg-white rounded-sm px-3 py-2 font-sans text-sm focus:outline-none focus:border-gold"
            />
            <button
              type="submit"
              disabled={newPatBusy || !newPatName.trim() || pats.filter((p) => !p.revoked_at).length >= 10}
              data-testid="pat-create-btn"
              className="bg-gold text-cream font-sans font-semibold text-sm px-5 py-2 rounded-sm hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              {newPatBusy ? "Creating…" : "Create token"}
            </button>
          </div>
          {scopeCatalog.length > 0 && (
            <div data-testid="pat-scopes-picker">
              <p className="font-sans text-[11px] uppercase tracking-[0.18em] font-semibold text-muted-ink mb-2">
                Scopes
                <span className="ml-2 normal-case tracking-normal text-[11px] text-muted-ink italic">
                  (leave empty for full access)
                </span>
              </p>
              <div className="flex flex-wrap gap-2">
                {scopeCatalog.map((s) => {
                  const on = newPatScopes.includes(s.key);
                  return (
                    <button
                      key={s.key}
                      type="button"
                      onClick={() => toggleScope(s.key)}
                      data-testid={`pat-scope-${s.key.replace(":","-")}`}
                      title={s.description}
                      className={`font-mono text-[11px] px-2.5 py-1 rounded-sm border transition-colors ${
                        on ? "bg-ink text-cream border-ink" : "bg-white text-ink border-gold/40 hover:border-gold"
                      }`}
                    >
                      {on ? "✓ " : ""}{s.key}
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </form>

        {pats.length === 0 ? (
          <p className="font-serif text-sm text-muted-ink italic" data-testid="pat-empty">
            You haven&apos;t created any access tokens yet.
          </p>
        ) : (
          <div className="border hairline rounded-sm divide-y divide-[#E8D4A0]" data-testid="pat-list">
            {pats.map((p) => {
              const revoked = !!p.revoked_at;
              return (
                <div key={p.id} data-testid={`pat-${p.id}`} className="px-5 py-4 flex items-center justify-between gap-4 flex-wrap">
                  <div className="min-w-0">
                    <div className="font-display font-semibold text-base ink">{p.name}</div>
                    <div className="font-mono text-xs text-muted-ink mt-1">
                      {p.prefix}…{" "}
                      <span className="text-muted-ink">
                        · Created {new Date(p.created_at).toLocaleDateString()}
                        {p.last_used_at ? ` · Last used ${new Date(p.last_used_at).toLocaleDateString()}` : " · Never used"}
                      </span>
                    </div>
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      {(p.scopes || ["*"]).map((s) => (
                        <span key={s} className="font-mono text-[10px] bg-cream-soft border border-gold/30 text-ink px-1.5 py-0.5 rounded-sm">
                          {s === "*" ? "full access" : s}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {revoked ? (
                      <span className="font-sans text-[10px] uppercase tracking-wide text-deepred border border-deepred px-1.5 py-0.5 rounded-sm">Revoked</span>
                    ) : (
                      <button
                        type="button"
                        onClick={() => revokePat(p.id)}
                        data-testid={`pat-revoke-${p.id}`}
                        className="font-sans text-xs uppercase tracking-wider font-semibold text-muted-ink hover:text-deepred transition-colors px-2"
                      >
                        Revoke
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        <details className="mt-6 font-sans text-sm text-muted-ink" data-testid="pat-usage-help">
          <summary className="cursor-pointer text-ink font-semibold">Quick connect — Claude, ChatGPT, n8n, scripts</summary>
          <div className="mt-4">
            <PatRecipes prefilledToken={revealedToken} />
          </div>
        </details>
      </section>
    </div>
  );
}

// ── PAT recipes ────────────────────────────────────────────────────────────
// Copy-pasteable snippets so a member can wire up Claude / ChatGPT / n8n / a
// script in under 30 seconds. If we have a freshly-created token in state we
// inline it; otherwise we show a `<your-thn-pat-token>` placeholder.
function PatRecipes({ prefilledToken }) {
  const [tab, setTab] = useState("claude");
  const tokenStr = prefilledToken || "<your-thn-pat-token>";
  // Use the current origin so dev previews still work; production resolves to
  // https://thehousingnews.com automatically.
  const apiBase = typeof window !== "undefined" ? window.location.origin : "https://thehousingnews.com";

  const copy = (txt) => {
    navigator.clipboard.writeText(txt).then(
      () => toast.success("Copied"),
      () => toast.error("Copy failed"),
    );
  };

  const claudeMcpConfig = `// Claude Desktop config — add to ~/Library/Application Support/Claude/claude_desktop_config.json
// (Windows: %APPDATA%\\Claude\\claude_desktop_config.json)
{
  "mcpServers": {
    "thehousingnews": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "${apiBase}/api/mcp",
        "--header",
        "Authorization: Bearer ${tokenStr}"
      ]
    }
  }
}

// After saving, fully quit and reopen Claude Desktop. Then ask Claude:
//   "What can you do for The Housing News?"
// Claude will list 7 tools (read briefing, search news, save draft, publish
// essay, list my posts, read my replies, list my drafts).`;

  const customGptYaml = `openapi: 3.0.0
info:
  title: The Housing News
  version: "1.0"
servers:
  - url: ${apiBase}
paths:
  /api/posts:
    post:
      operationId: createPost
      summary: Publish a post or essay to The Housing News
      security:
        - bearerAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [kind, text]
              properties:
                kind: { type: string, enum: [short, essay] }
                title: { type: string }
                subtitle: { type: string }
                text: { type: string }
                tags: { type: array, items: { type: string } }
      responses:
        "200":
          description: Created
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer`;

  const n8nConfig = `Method: POST
URL: ${apiBase}/api/posts
Authentication: Header Auth
  Name: Authorization
  Value: Bearer ${tokenStr}
Headers:
  Content-Type: application/json
Body (JSON):
  {
    "kind": "short",
    "text": "{{ $json.text }}",
    "tags": []
  }`;

  const curlBlock = `# Bash / curl
curl -X POST ${apiBase}/api/posts \\
  -H "Authorization: Bearer ${tokenStr}" \\
  -H "Content-Type: application/json" \\
  -d '{"kind":"short","text":"Hello from my CLI.","tags":["test"]}'

# Python (requests)
import requests
requests.post(
  "${apiBase}/api/posts",
  headers={"Authorization": "Bearer ${tokenStr}"},
  json={"kind": "short", "text": "Hello from Python.", "tags": []},
).json()`;

  const recipes = [
    { id: "claude",  label: "Claude Desktop (MCP)",  body: claudeMcpConfig,    note: "Real MCP server — Claude gets 7 native tools (read briefing, search news, save draft, publish essay, list posts/replies). Requires Node.js installed locally. Paste into Claude Desktop config, then restart the app." },
    { id: "gpt",     label: "ChatGPT (Actions)",  body: customGptYaml,       note: "In your Custom GPT → Configure → Actions → Add. Paste this OpenAPI schema and add the token under Authentication." },
    { id: "n8n",     label: "n8n / Zapier / Make", body: n8nConfig,          note: "Use any HTTP Request node. Same recipe works for Zapier, Make, Pipedream, etc." },
    { id: "curl",    label: "Curl / Script",      body: curlBlock,           note: "Drop-in snippets for any shell or backend job." },
  ];

  const active = recipes.find((r) => r.id === tab) || recipes[0];

  return (
    <div data-testid="pat-recipes" className="border hairline rounded-sm bg-cream-soft p-4">
      <div className="flex items-center gap-1 flex-wrap mb-3" role="tablist">
        {recipes.map((r) => (
          <button
            key={r.id}
            type="button"
            role="tab"
            aria-selected={tab === r.id}
            onClick={() => setTab(r.id)}
            data-testid={`pat-recipe-tab-${r.id}`}
            className={`font-sans text-[12px] uppercase tracking-[0.12em] font-semibold px-3 py-1.5 rounded-sm transition-colors ${
              tab === r.id ? "bg-ink text-cream" : "text-muted-ink hover:text-ink"
            }`}
          >
            {r.label}
          </button>
        ))}
      </div>
      <p className="font-serif text-[13px] text-ink/75 italic mb-3">{active.note}</p>
      <div className="relative">
        <pre
          data-testid={`pat-recipe-body-${active.id}`}
          className="bg-white border hairline rounded-sm p-3 overflow-x-auto text-[11.5px] leading-relaxed font-mono whitespace-pre-wrap break-words max-h-[360px] overflow-y-auto"
        >
{active.body}
        </pre>
        <button
          type="button"
          onClick={() => copy(active.body)}
          data-testid={`pat-recipe-copy-${active.id}`}
          className="absolute top-2 right-2 bg-ink text-cream font-sans font-semibold text-[11px] uppercase tracking-wider px-2.5 py-1 rounded-sm hover:bg-gold transition-colors"
        >
          Copy
        </button>
      </div>
      {!prefilledToken && (
        <p className="font-sans text-[11px] text-muted-ink mt-3">
          Replace <code className="bg-white px-1.5 py-0.5 rounded-sm">{"<your-thn-pat-token>"}</code> with a token from the list above.
        </p>
      )}
    </div>
  );
}

function ToggleRow({ label, hint, checked, onChange, disabled, testid }) {
  return (
    <div className="flex items-center justify-between gap-6 px-5 py-5">
      <div>
        <div className="font-display font-semibold text-base ink">{label}</div>
        <div className="font-sans text-sm text-muted-ink mt-1">{hint}</div>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        data-testid={testid}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors disabled:opacity-50 ${checked ? "bg-gold" : "bg-[#E8D4A0]"}`}
      >
        <span className={`inline-block h-5 w-5 transform rounded-full bg-cream transition-transform ${checked ? "translate-x-5" : "translate-x-0.5"}`} />
      </button>
    </div>
  );
}
