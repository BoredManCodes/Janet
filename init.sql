create schema polls;

create table polls.poll_data
(
    title              text   not null,
    author_id          bigint not null,
    description        text,
    channel_id         bigint not null,
    message_id         bigint not null
        constraint poll_data_pk
            primary key,
    thread_message_id  bigint,
    guild_id           bigint not null,
    single_vote        boolean,
    hide_results       boolean,
    open_poll          boolean,
    inline             boolean,
    thread             boolean,
    close_message      boolean,
    sent_close_message boolean,
    colour             text,
    image_url          text,
    expire_time        timestamp,
    expired            boolean,
    closed             boolean,
    author_name        text,
    author_avatar      text,
    poll_options       json
);