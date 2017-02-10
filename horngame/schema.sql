drop table if exists users;
create table users (
  id integer primary key autoincrement,
  username text not null,
  password text not null,
  nsolved integer DEFAULT(0), 
  nerrors integer DEFAULT(0),
  admin integer DEFAULT(0)
);

drop table if exists attempts;
create table attempts (
  id integer primary key autoincrement,
  user_id integer not null,
  task_id text not null,
  json text not null,
  result text not null,
  submitDate datetime not null,
  duration integer not null,
  success integer DEFAULT(0),
  verified integer DEFAULT(0)
);

drop table if exists problems_solved;
create table problems_solved (
  id integer primary key autoincrement,
  attempt_id integer not null,
  problem_id text not null,
  verificationDate datetime not null
);

