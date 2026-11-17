CREATE TABLE IF NOT EXISTS test_cli_table (
    id SERIAL PRIMARY KEY,
    message TEXT
);
INSERT INTO test_cli_table (message) VALUES ('Hello World!');