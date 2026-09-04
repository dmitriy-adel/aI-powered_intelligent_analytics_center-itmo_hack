BEGIN;

INSERT INTO sources (name, url, url_rss, source_type, category_default)
VALUES
    ('Ведомости', 'https://www.vedomosti.ru/', 'https://www.vedomosti.ru/rss/news.xml', 'СМИ', 'Экономика'),
    ('Коммерсантъ', 'https://www.kommersant.ru/', 'https://www.kommersant.ru/rss/news.xml', 'СМИ', 'Экономика'),
    ('Телеспутник', 'https://telesputnik.ru/', 'https://telesputnik.ru/rss/', 'СМИ', 'Технологии'),
    ('regulation.gov.ru', 'https://regulation.gov.ru/', NULL, 'Регулятор', 'Регулирование'),
    ('СОЗД Госдумы', 'https://sozd.duma.gov.ru/', NULL, 'Регулятор', 'Регулирование'),
    ('publication.pravo.gov.ru', 'https://publication.pravo.gov.ru/', NULL, 'Регулятор', 'Регулирование'),
    ('government.ru', 'http://government.ru/news/', 'http://government.ru/all/rss/', 'Регулятор', 'Регулирование')
ON CONFLICT (name) DO NOTHING;

COMMIT;
