ALTER TABLE emails ADD delivered_to TEXT DEFAULT NULL;

ALTER TABLE emails RENAME COLUMN sender_full TO from_full;
ALTER TABLE emails RENAME COLUMN sender_name TO from_name;
ALTER TABLE emails RENAME COLUMN sender_addr TO from_addr;

ALTER TABLE emails ADD sender_full TEXT DEFAULT NULL;
ALTER TABLE emails ADD sender_name TEXT DEFAULT NULL;
ALTER TABLE emails ADD sender_addr TEXT DEFAULT NULL;
