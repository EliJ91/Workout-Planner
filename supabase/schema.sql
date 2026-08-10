create table if not exists public.workout_planner_data (
  user_id uuid primary key references auth.users(id) on delete cascade,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.workout_planner_data enable row level security;

create or replace function public.set_workout_planner_updated_at()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists set_workout_planner_updated_at on public.workout_planner_data;
create trigger set_workout_planner_updated_at
before update on public.workout_planner_data
for each row execute function public.set_workout_planner_updated_at();

drop policy if exists "Workout planner data is readable by owner" on public.workout_planner_data;
create policy "Workout planner data is readable by owner"
on public.workout_planner_data
for select
to authenticated
using (auth.uid() = user_id);

drop policy if exists "Workout planner data is insertable by owner" on public.workout_planner_data;
create policy "Workout planner data is insertable by owner"
on public.workout_planner_data
for insert
to authenticated
with check (auth.uid() = user_id);

drop policy if exists "Workout planner data is updatable by owner" on public.workout_planner_data;
create policy "Workout planner data is updatable by owner"
on public.workout_planner_data
for update
to authenticated
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

drop policy if exists "Workout planner data is deletable by owner" on public.workout_planner_data;
create policy "Workout planner data is deletable by owner"
on public.workout_planner_data
for delete
to authenticated
using (auth.uid() = user_id);

grant usage on schema public to authenticated;
grant select, insert, update, delete on public.workout_planner_data to authenticated;
revoke all on public.workout_planner_data from anon;
