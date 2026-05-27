import { useEffect, useMemo, useState } from "react";
import type { LibraryIndex, Story } from "./types";

export function App() {
  const [index, setIndex]   = useState<LibraryIndex | null>(null);
  const [error, setError]   = useState<string | null>(null);
  const [query, setQuery]   = useState("");
  const [activeTags, setActiveTags] = useState<Set<string>>(new Set());
  const [selected,  setSelected]    = useState<Set<string>>(new Set());
  const [previewStoryId, setPreviewStoryId] = useState<string | null>(null);

  useEffect(() => {
    fetch("/library/index.json")
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(setIndex)
      .catch(e => setError(String(e)));
  }, []);

  const filtered = useMemo(() => {
    if (!index) return [];
    const q = query.trim().toLowerCase();
    return index.stories.filter(s => {
      if (activeTags.size > 0) {
        for (const t of activeTags) if (!s.tags.includes(t)) return false;
      }
      if (q && !(`${s.title} ${s.story_id} ${s.tags.join(" ")}`.toLowerCase().includes(q))) {
        return false;
      }
      return true;
    });
  }, [index, query, activeTags]);

  function toggleTag(t: string) {
    setActiveTags(prev => {
      const next = new Set(prev);
      next.has(t) ? next.delete(t) : next.add(t);
      return next;
    });
  }

  function toggleSelect(id: string) {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  if (error) return <div className="error">Failed to load /library/index.json — {error}</div>;
  if (!index) return <div className="loading">Loading library…</div>;

  return (
    <div className="app">
      <Sidebar
        index={index}
        query={query}
        setQuery={setQuery}
        activeTags={activeTags}
        toggleTag={toggleTag}
      />
      <main className="main">
        <Toolbar
          total={index.story_count}
          filtered={filtered.length}
          selected={selected}
          clearSelected={() => setSelected(new Set())}
        />
        <BlockView
          stories={filtered}
          selected={selected}
          toggleSelect={toggleSelect}
          onPreview={setPreviewStoryId}
        />
      </main>
      {previewStoryId && (
        <PreviewPane
          story={index.stories.find(s => s.story_id === previewStoryId)!}
          onClose={() => setPreviewStoryId(null)}
        />
      )}
    </div>
  );
}

function Sidebar(props: {
  index: LibraryIndex;
  query: string;
  setQuery: (q: string) => void;
  activeTags: Set<string>;
  toggleTag: (t: string) => void;
}) {
  const { index, query, setQuery, activeTags, toggleTag } = props;
  const axes = Object.keys(index.tag_axes).sort();
  return (
    <aside className="sidebar">
      <div className="brand">RollingAI<br/><span>Deck Library</span></div>
      <input
        className="search"
        placeholder="搜索标题 / 标签 / id…"
        value={query}
        onChange={e => setQuery(e.target.value)}
      />
      <div className="axes">
        {axes.map(axis => (
          <div key={axis} className="axis">
            <div className="axis-name">{axis}</div>
            {index.tag_axes[axis].map(t => (
              <button
                key={t.tag}
                className={`tag ${activeTags.has(t.tag) ? "active" : ""}`}
                onClick={() => toggleTag(t.tag)}
              >
                <span className="tag-value">{t.value}</span>
                <span className="tag-count">{t.count}</span>
              </button>
            ))}
          </div>
        ))}
      </div>
    </aside>
  );
}

function Toolbar(props: {
  total: number;
  filtered: number;
  selected: Set<string>;
  clearSelected: () => void;
}) {
  const { total, filtered, selected, clearSelected } = props;
  const n = selected.size;
  const ids = Array.from(selected);
  const mergeCmd =
    `python3 plugin/skills/rolling-deck/assets/library-merge.py \\\n` +
    `  --stories ${ids.join(" ")} \\\n` +
    `  --output runs/$(date +%Y%m%d-%H%M%S)-merge/output/`;
  return (
    <div className="toolbar">
      <div className="counts">
        {filtered === total ? `${total} stories` : `${filtered} / ${total} stories`}
      </div>
      <div className="actions">
        {n === 0 ? (
          <span className="hint">选择多个 story 后可以合并 / 重生</span>
        ) : (
          <>
            <span className="hint">已选 {n} 个</span>
            <button className="btn ghost" onClick={clearSelected}>清空</button>
            <button
              className="btn primary"
              disabled={n < 2}
              title={n < 2 ? "至少选 2 个 story" : ""}
              onClick={() => navigator.clipboard.writeText(mergeCmd)}
            >
              复制合并命令
            </button>
          </>
        )}
      </div>
    </div>
  );
}

function BlockView(props: {
  stories: Story[];
  selected: Set<string>;
  toggleSelect: (id: string) => void;
  onPreview: (id: string) => void;
}) {
  const { stories, selected, toggleSelect, onPreview } = props;
  if (stories.length === 0) {
    return <div className="empty">没有匹配的 story</div>;
  }
  return (
    <div className="grid">
      {stories.map(s => (
        <StoryCard
          key={s.story_id}
          story={s}
          selected={selected.has(s.story_id)}
          onSelect={() => toggleSelect(s.story_id)}
          onPreview={() => onPreview(s.story_id)}
        />
      ))}
    </div>
  );
}

function StoryCard(props: {
  story: Story;
  selected: boolean;
  onSelect: () => void;
  onPreview: () => void;
}) {
  const { story, selected, onSelect, onPreview } = props;
  return (
    <div className={`card ${selected ? "selected" : ""}`}>
      <div className="thumb-wrap" onClick={onPreview}>
        <img className="thumb" src={`/library/${story.thumbnail}`} alt={story.title}/>
        <div className="thumb-meta">{story.slide_count} pages</div>
      </div>
      <div className="card-body">
        <label className="card-select">
          <input type="checkbox" checked={selected} onChange={onSelect}/>
          <div className="card-title" title={story.story_id}>{story.title}</div>
        </label>
        <div className="card-tags">
          {story.tags.map(t => <span key={t} className="card-tag">{t}</span>)}
        </div>
      </div>
    </div>
  );
}

function PreviewPane(props: { story: Story; onClose: () => void }) {
  const { story, onClose } = props;
  return (
    <div className="preview" onClick={onClose}>
      <div className="preview-frame" onClick={e => e.stopPropagation()}>
        <div className="preview-head">
          <div>
            <div className="preview-title">{story.title}</div>
            <div className="preview-id">{story.story_id}</div>
          </div>
          <button className="btn ghost" onClick={onClose}>关闭</button>
        </div>
        <iframe className="preview-iframe" src={`/library/${story.deck_path}`} title={story.title}/>
      </div>
    </div>
  );
}
