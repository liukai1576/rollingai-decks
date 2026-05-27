export interface Story {
  story_id: string;
  title: string;
  tags: string[];
  slide_count: number;
  source: { kind: string; imported_from: string | null };
  thumbnail: string;
  deck_path: string;
  owners: string[];
  created_at: string | null;
  checks: { ingest_passed?: boolean; last_validated_at?: string };
}

export interface TagAxisEntry {
  value: string;
  tag: string;
  count: number;
}

export interface LibraryIndex {
  generated_at: string;
  story_count: number;
  tag_axes: Record<string, TagAxisEntry[]>;
  stories: Story[];
}
