-- Initial schema for AI Storytelling (specs/11-DATABASE.md)

CREATE TABLE IF NOT EXISTS stories (
    story_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    event_key TEXT NOT NULL UNIQUE,
    event_date TEXT,
    location TEXT,
    sensitive_flag INTEGER NOT NULL DEFAULT 0 CHECK (sensitive_flag IN (0, 1)),
    status TEXT NOT NULL DEFAULT 'DISCOVERED' CHECK (
        status IN (
            'DISCOVERED', 'RESEARCHING', 'NEEDS_REVIEW', 'APPROVED',
            'SCRIPTED', 'ASSETS_READY', 'RENDERED', 'QC_PASSED',
            'PUBLISHED', 'FAILED'
        )
    ),
    confidence REAL NOT NULL DEFAULT 0.0 CHECK (confidence >= 0.0 AND confidence <= 1.0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_stories_status ON stories(status);
CREATE INDEX IF NOT EXISTS idx_stories_event_key ON stories(event_key);

CREATE TABLE IF NOT EXISTS sources (
    source_id TEXT PRIMARY KEY,
    story_id TEXT NOT NULL REFERENCES stories(story_id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    source_type TEXT NOT NULL,
    title TEXT,
    published_at TEXT,
    retrieved_at TEXT NOT NULL,
    is_primary INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
    independence_group TEXT,
    license_notes TEXT,
    UNIQUE(story_id, url)
);

CREATE INDEX IF NOT EXISTS idx_sources_story_id ON sources(story_id);

CREATE TABLE IF NOT EXISTS claims (
    claim_id TEXT PRIMARY KEY,
    story_id TEXT NOT NULL REFERENCES stories(story_id) ON DELETE CASCADE,
    statement TEXT NOT NULL,
    is_central INTEGER NOT NULL DEFAULT 1 CHECK (is_central IN (0, 1)),
    status TEXT NOT NULL DEFAULT 'UNVERIFIED' CHECK (
        status IN ('VERIFIED', 'DISPUTED', 'UNVERIFIED')
    ),
    uncertainty_notes TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_claims_story_id ON claims(story_id);
CREATE INDEX IF NOT EXISTS idx_claims_status ON claims(status);

CREATE TABLE IF NOT EXISTS claim_sources (
    claim_id TEXT NOT NULL REFERENCES claims(claim_id) ON DELETE CASCADE,
    source_id TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
    supporting_excerpt TEXT NOT NULL,
    locator TEXT,
    PRIMARY KEY (claim_id, source_id)
);

CREATE TABLE IF NOT EXISTS episodes (
    episode_id TEXT PRIMARY KEY,
    story_id TEXT NOT NULL REFERENCES stories(story_id) ON DELETE CASCADE,
    series_index INTEGER NOT NULL DEFAULT 1 CHECK (series_index >= 1),
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'DISCOVERED' CHECK (
        status IN (
            'DISCOVERED', 'RESEARCHING', 'NEEDS_REVIEW', 'APPROVED',
            'SCRIPTED', 'ASSETS_READY', 'RENDERED', 'QC_PASSED',
            'PUBLISHED', 'FAILED'
        )
    ),
    target_duration_sec REAL NOT NULL DEFAULT 60.0 CHECK (target_duration_sec > 0.0),
    actual_duration_sec REAL,
    word_count INTEGER,
    script_json TEXT,
    artifact_hash TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(story_id, series_index)
);

CREATE INDEX IF NOT EXISTS idx_episodes_story_id ON episodes(story_id);
CREATE INDEX IF NOT EXISTS idx_episodes_status ON episodes(status);

CREATE TABLE IF NOT EXISTS scenes (
    scene_id TEXT PRIMARY KEY,
    episode_id TEXT NOT NULL REFERENCES episodes(episode_id) ON DELETE CASCADE,
    scene_index INTEGER NOT NULL CHECK (scene_index >= 0),
    narration_text TEXT NOT NULL,
    claim_ids_json TEXT NOT NULL DEFAULT '[]',
    visual_prompt TEXT NOT NULL,
    start_sec REAL NOT NULL DEFAULT 0.0 CHECK (start_sec >= 0.0),
    duration_sec REAL NOT NULL CHECK (duration_sec > 0.0),
    camera_motion TEXT NOT NULL DEFAULT 'gentle_zoom_in',
    created_at TEXT NOT NULL,
    UNIQUE(episode_id, scene_index)
);

CREATE INDEX IF NOT EXISTS idx_scenes_episode_id ON scenes(episode_id);

CREATE TABLE IF NOT EXISTS assets (
    asset_id TEXT PRIMARY KEY,
    episode_id TEXT NOT NULL REFERENCES episodes(episode_id) ON DELETE CASCADE,
    scene_id TEXT REFERENCES scenes(scene_id) ON DELETE SET NULL,
    asset_type TEXT NOT NULL CHECK (
        asset_type IN (
            'IMAGE', 'AUDIO_NARRATION', 'AUDIO_AMBIENT',
            'SUBTITLE', 'VIDEO_MP4', 'MANIFEST'
        )
    ),
    file_path TEXT NOT NULL,
    sha256_checksum TEXT NOT NULL,
    byte_size INTEGER NOT NULL CHECK (byte_size >= 0),
    model_name TEXT,
    model_version TEXT,
    license_id TEXT NOT NULL,
    rights_provenance TEXT NOT NULL,
    metadata_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_assets_episode_id ON assets(episode_id);
CREATE INDEX IF NOT EXISTS idx_assets_type ON assets(asset_type);

CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    job_key TEXT NOT NULL UNIQUE,
    story_id TEXT REFERENCES stories(story_id) ON DELETE CASCADE,
    episode_id TEXT REFERENCES episodes(episode_id) ON DELETE CASCADE,
    stage TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (
        status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'PAUSED')
    ),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    max_attempts INTEGER NOT NULL DEFAULT 3 CHECK (max_attempts >= 1),
    uses_gpu INTEGER NOT NULL DEFAULT 0 CHECK (uses_gpu IN (0, 1)),
    gpu_seconds REAL NOT NULL DEFAULT 0.0 CHECK (gpu_seconds >= 0.0),
    spend_inr REAL NOT NULL DEFAULT 0.0 CHECK (spend_inr >= 0.0),
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_uses_gpu_status ON jobs(uses_gpu, status);

CREATE TABLE IF NOT EXISTS quality_checks (
    check_id TEXT PRIMARY KEY,
    episode_id TEXT NOT NULL REFERENCES episodes(episode_id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('PASS', 'FAIL', 'REVIEW')),
    reasons_json TEXT NOT NULL DEFAULT '[]',
    report_json TEXT NOT NULL,
    checked_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_quality_checks_episode_id ON quality_checks(episode_id);

CREATE TABLE IF NOT EXISTS publish_records (
    publish_id TEXT PRIMARY KEY,
    episode_id TEXT NOT NULL REFERENCES episodes(episode_id) ON DELETE CASCADE,
    platform TEXT NOT NULL CHECK (platform IN ('EXPORT_ONLY', 'YOUTUBE_SHORTS', 'META_REELS')),
    dry_run INTEGER NOT NULL DEFAULT 1 CHECK (dry_run IN (0, 1)),
    external_post_id TEXT,
    synthetic_disclosure INTEGER NOT NULL DEFAULT 1 CHECK (synthetic_disclosure IN (0, 1)),
    status TEXT NOT NULL CHECK (status IN ('EXPORTED', 'DRY_RUN_OK', 'PUBLISHED', 'FAILED')),
    metadata_json TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(episode_id, platform, dry_run)
);

CREATE INDEX IF NOT EXISTS idx_publish_records_episode_id ON publish_records(episode_id);
