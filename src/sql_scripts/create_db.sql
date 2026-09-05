
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

    CONSTRAINT sources_name_unique UNIQUE (name)
);


CREATE INDEX idx_sources_status ON sources (status);
CREATE INDEX idx_sources_source_type ON sources (source_type);


CREATE TABLE news (
    id                  BIGSERIAL PRIMARY KEY,
    title               TEXT,
    text                TEXT,                       -- полный текст новости
    source              TEXT NOT NULL,              -- наименование источника (см. примечание ниже)
    url                 TEXT NOT NULL,               -- ссылка на новость
    category            TEXT,
    description         TEXT,
    lifetime            TIMESTAMPTZ,                 -- пока просто дата/время; в будущем может стать интервалом
    company_mentions    JSONB,                       -- упоминания компаний и конкурентов
    regulatory_changes  JSONB,                       -- изменения в НПБ (нормативно-правовой базе)
    consequences        JSONB,                       -- последствия
    industry_trends     JSONB,                       -- отраслевые тренды и сигналы
    priority            news_priority_enum DEFAULT 'low',
    tags                TEXT[] DEFAULT '{}', -- список тегов
    created_at          TIMESTAMPTZ DEFAULT now(),
    author              TEXT DEFAULT 'system',
    is_hidden           BOOLEAN NOT NULL DEFAULT FALSE,
    in_general          BOOLEAN NOT NULL DEFAULT TRUE,
    fact_when           TEXT,

    CONSTRAINT news_url_unique UNIQUE (url)
);

CREATE TABLE entities (
    id                  BIGSERIAL PRIMARY KEY,
    object_id           TEXT NOT NULL UNIQUE,
    object_type         TEXT NOT NULL,
    canonical_title     TEXT NOT NULL DEFAULT '—',
    agency              TEXT NOT NULL DEFAULT '',
    kind                TEXT NOT NULL DEFAULT '',
    ids                 JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding           DOUBLE PRECISION[],
    events              JSONB NOT NULL DEFAULT '[]'::jsonb,
    publication_links   JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT entities_type_check CHECK (object_type IN ('news_plot', 'npa'))
);

CREATE INDEX idx_entities_object_type ON entities (object_type);

ALTER TABLE news ADD COLUMN source_id BIGINT REFERENCES sources(id);
ALTER TABLE news ADD COLUMN entity_id BIGINT REFERENCES entities(id);
ALTER TABLE news ADD COLUMN relevance_score FLOAT;

CREATE INDEX idx_news_source_id ON news (source_id);
CREATE INDEX idx_news_entity_id ON news (entity_id);

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

insert into sources(name, url, url_rss, source_type, status) values
('Цифровые индустриальные технологии - дайджест', 'https://t.me/cit_gov', '-', 'Telegram', 'active'),
('РФРИТ', 'https://t.me/rfrit', '-', 'Telegram', 'active'),
('Гранты для ИТ', 'https://t.me/grantsforbussines', '-', 'Telegram', 'active'),
('CIO: канал IT руководителей', 'https://t.me/cio_channel', '-', 'Telegram', 'active'),
('Торгпред - тендеры и закупки', 'https://t.me/rustorgpred', '-', 'Telegram', 'active'),
('Правительство РФ - сводки', 'https://t.me/government_rus', '-', 'Telegram', 'active'),
('АРПЭ - новости', 'https://t.me/arperf', '-', 'Telegram', 'active'),
('ЦИПР - новости и анонсы мероприятий', 'https://t.me/icipr', '-', 'Telegram', 'active'),
('Правовой комитет АРПП', 'https://arppsoft.ru/boards/law/', '-', 'Регулятор', 'error'),
('АРПП - новости', 'https://t.me/arppsoft', '-', 'СМИ', 'error'),
('Ведомости', 'https://www.vedomosti.ru', 'https://www.vedomosti.ru/rss/news.xml', 'СМИ', 'active'),
('Коммерсант', 'https://www.kommersant.ru', 'https://www.kommersant.ru/rss/news.xml', 'СМИ', 'active'),
('Кабельщик', 'https://www.cableman.ru', '-', 'СМИ', 'error'),
('Телеспутник', 'https://telesputnik.ru', 'https://telesputnik.ru/rss/', 'СМИ', 'active');

COMMIT;
