
BEGIN;
 

CREATE TYPE source_type_enum AS ENUM ('СМИ', 'Регулятор', 'Telegram');
CREATE TYPE source_status_enum AS ENUM ('active', 'paused', 'error');
CREATE TYPE news_priority_enum AS ENUM ('low', 'mid', 'high');
CREATE TYPE user_status_enum AS ENUM ('user', 'admin');
 
 
CREATE TABLE sources (
    id              BIGSERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    url             TEXT,                       -- ссылка на главную страницу
    url_rss         TEXT,                       -- ссылка на RSS-ленту
    source_type     source_type_enum NOT NULL,
    status          source_status_enum NOT NULL DEFAULT 'active',
    last_update_dt  TIMESTAMPTZ,                -- дата последней новости из источника
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    category_default TEXT NOT NULL DEFAULT 'Экономика',
    poll_interval    TEXT NOT NULL DEFAULT 'Каждые 15 минут',

    CONSTRAINT sources_name_unique UNIQUE (name),
    CONSTRAINT sources_url_rss_unique UNIQUE (url_rss)
);

 
CREATE INDEX idx_sources_status ON sources (status);
CREATE INDEX idx_sources_source_type ON sources (source_type);
 

CREATE TABLE news (
    id                  BIGSERIAL PRIMARY KEY,
    title               TEXT NOT NULL,
    text                TEXT,                       -- полный текст новости
    source              TEXT NOT NULL,              -- наименование источника (см. примечание ниже)
    url                 TEXT NOT NULL,               -- ссылка на новость
    description         TEXT,
    lifetime            TIMESTAMPTZ,                 -- пока просто дата/время; в будущем может стать интервалом
    company_mentions    JSONB,                       -- упоминания компаний и конкурентов
    regulatory_changes  JSONB,                       -- изменения в НПБ (нормативно-правовой базе)
    consequences        JSONB,                       -- последствия
    industry_trends     JSONB,                       -- отраслевые тренды и сигналы
    priority            news_priority_enum NOT NULL DEFAULT 'mid',
    tags                TEXT[] NOT NULL DEFAULT '{}', -- список тегов
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    author              TEXT NOT NULL DEFAULT 'system',
    category            TEXT NOT NULL DEFAULT 'Экономика',
    is_hidden           BOOLEAN NOT NULL DEFAULT FALSE,
    in_general          BOOLEAN NOT NULL DEFAULT TRUE,
    fact_when           TEXT,

    CONSTRAINT news_url_unique UNIQUE (url)
);

ALTER TABLE news ADD COLUMN source_id BIGINT REFERENCES sources(id);
CREATE INDEX idx_news_source_id ON news (source_id);

CREATE INDEX idx_news_source ON news (source);
CREATE INDEX idx_news_priority ON news (priority);
CREATE INDEX idx_news_created_at ON news (created_at);
CREATE INDEX idx_news_lifetime ON news (lifetime);
CREATE INDEX idx_news_tags ON news USING GIN (tags);
CREATE INDEX idx_news_company_mentions ON news USING GIN (company_mentions);
CREATE INDEX idx_news_regulatory_changes ON news USING GIN (regulatory_changes);
CREATE INDEX idx_news_consequences ON news USING GIN (consequences);
CREATE INDEX idx_news_industry_trends ON news USING GIN (industry_trends);
CREATE INDEX IF NOT EXISTS idx_news_in_general ON news (in_general);
CREATE INDEX IF NOT EXISTS idx_news_is_hidden ON news (is_hidden);
 
 
CREATE TABLE users (
    id          BIGSERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    email       TEXT NOT NULL,
    pswd        TEXT NOT NULL,                 
    status      user_status_enum NOT NULL DEFAULT 'user',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
 
    CONSTRAINT users_email_unique UNIQUE (email)
);
 

CREATE INDEX idx_users_status ON users (status);
 
COMMIT;
