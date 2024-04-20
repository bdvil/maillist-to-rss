CREATE TABLE emails (
    id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    date TIMESTAMP,
    user_agent TEXT,
    content_language TEXT,
    recipient TEXT,
    sender_full TEXT,
    sender_name TEXT,
    sender_addr TEXT,
    subject TEXT,
    body TEXT
);
