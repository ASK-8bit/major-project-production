-- ============================================================
-- profiles (already created earlier)
-- ============================================================
-- create table public.profiles (
--   user_id uuid references auth.users(id) primary key,
--   email text not null,
--   full_name text,
--   github_token text,
--   created_at timestamp default now()
-- );


-- ============================================================
-- sessions — one row per repo upload
-- ============================================================
create table public.sessions (
  session_id uuid primary key,
  user_id uuid references auth.users(id) not null,
  repo_url text not null,
  total_chunks int default 0,
  status text default 'processing',  -- processing | ready | failed
  created_at timestamp default now()
);

create index idx_sessions_user_id on public.sessions(user_id);


-- ============================================================
-- jobs — tracks indexing progress for each upload
-- ============================================================
create table public.jobs (
  job_id uuid primary key,
  session_id uuid references public.sessions(session_id) on delete cascade,
  status text default 'pending',  -- pending | cloning | parsing | embedding | storing | ready | failed
  chunks_done int default 0,
  total_chunks int default 0,
  error text,
  created_at timestamp default now()
);

create index idx_jobs_session_id on public.jobs(session_id);


-- ============================================================
-- chats — one conversation thread under a session
-- ============================================================
create table public.chats (
  chat_id uuid primary key,
  session_id uuid references public.sessions(session_id) on delete cascade,
  user_id uuid references auth.users(id) not null,
  title text,
  created_at timestamp default now()
);

create index idx_chats_session_id on public.chats(session_id);


-- ============================================================
-- messages — individual messages within a chat
-- ============================================================
create table public.messages (
  message_id uuid primary key,
  chat_id uuid references public.chats(chat_id) on delete cascade,
  role text not null,  -- 'user' | 'assistant'
  content text not null,
  created_at timestamp default now()
);

create index idx_messages_chat_id on public.messages(chat_id);