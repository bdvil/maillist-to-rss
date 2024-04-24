ALTER TABLE aliases RENAME COLUMN pass TO alias;
ALTER TABLE aliases RENAME COLUMN sender TO link_val;
ALTER TABLE aliases ADD link_key TEXT DEFAULT 'from_addr';
