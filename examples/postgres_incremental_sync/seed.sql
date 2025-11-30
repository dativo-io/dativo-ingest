CREATE TABLE IF NOT EXISTS public.customers (
    customer_id BIGSERIAL PRIMARY KEY,
    email TEXT,
    full_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'trial',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

TRUNCATE TABLE public.customers;

INSERT INTO public.customers (email, full_name, status, updated_at) VALUES
    ('alice@example.com', 'Alice Jensen', 'active', NOW() - INTERVAL '1 day'),
    ('bob@example.com', 'Bob Rivera', 'trial', NOW() - INTERVAL '2 hours'),
    ('carol@example.com', 'Carol Tranh', 'churned', NOW() - INTERVAL '5 days');
