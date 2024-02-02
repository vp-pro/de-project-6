#### Interact with Vertica DB:
#### drop and create tables
#### load data to vertica from docker container
#### in AIRFLOW create vertica connection first and instal libs in container


from datetime import datetime, timedelta
import os
from airflow import DAG
from airflow.operators.dummy_operator import DummyOperator
from airflow.operators.python import PythonOperator
import logging
import vertica_python
from airflow.contrib.hooks.vertica_hook import VerticaHook

def execute_vertica():
    path = os.getcwd()
    logging.info(f"working path - {path}")
    cur = VerticaHook('vertica_conn_id').get_cursor()
    logging.info("Start connection - db Vertica")
    cur.execute("""

    drop table if exists stv2023121113__DWH.h_users CASCADE;
    drop table if exists stv2023121113__DWH.h_groups CASCADE;
    drop table if exists stv2023121113__DWH.l_user_group_activity CASCADE;
    drop table if exists stv2023121113__DWH.s_auth_history CASCADE;

    ------------------------------
    ---USERS HUB
    ------------------------------

    create table stv2023121113__DWH.h_users
    (
        hk_user_id bigint primary key,
        user_id      int,
        load_dt datetime,
        load_src varchar(20)
    )
    order by load_dt
    SEGMENTED BY hk_user_id all nodes
    PARTITION BY load_dt::date
    GROUP BY calendar_hierarchy_day(load_dt::date, 3, 2);


    INSERT INTO stv2023121113__DWH.h_users(hk_user_id, user_id, load_dt, load_src)
    select distinct
        hash(user_id) as  hk_user_id,
        user_id,
        now() as load_dt,
        's3' as load_src
        from stv2023121113__STAGING.group_log
    where hash(user_id) not in (select hk_user_id from stv2023121113__DWH.h_users);

    ------------------------------
    ---GROUPS HUB
    ------------------------------

    create table stv2023121113__DWH.h_groups
    (
        hk_group_id       bigint primary key,
        group_id          int,
        registration_dt datetime,
        load_dt           datetime,
        load_src          varchar(20)
    )
    order by load_dt
    SEGMENTED BY hk_group_id all nodes
    PARTITION BY load_dt::date
    GROUP BY calendar_hierarchy_day(load_dt::date, 3, 2);


    INSERT INTO stv2023121113__DWH.h_groups(hk_group_id, group_id, registration_dt, load_dt, load_src)
    select distinct
        hash(group_id) as hk_group_id,
        group_id,
        datetime,
        now() as load_dt,
        's3' as load_src
        from stv2023121113__STAGING.group_log
    where hash(group_id) not in (select hk_group_id from stv2023121113__DWH.h_groups)
    and event = 'create';

    ------------------------------
    ---USER ACTIVITY LINK
    ------------------------------

    create table stv2023121113__DWH.l_user_group_activity
    (
        hk_l_user_group_activity bigint primary key,
        hk_user_id bigint not null CONSTRAINT fk_h_users REFERENCES stv2023121113__DWH.h_users (hk_user_id),
        hk_group_id bigint not null CONSTRAINT fk_h_groups REFERENCES stv2023121113__DWH.h_groups (hk_group_id),
        load_dt           datetime,
        load_src          varchar(20)
    )
    order by load_dt
    SEGMENTED BY hk_l_user_group_activity all nodes
    PARTITION BY load_dt::date
    GROUP BY calendar_hierarchy_day(load_dt::date, 3, 2);

    INSERT INTO stv2023121113__DWH.l_user_group_activity(hk_l_user_group_activity, hk_user_id, hk_group_id, load_dt, load_src)
    select distinct
        hash(hu.hk_user_id, hg.hk_group_id),
        hu.hk_user_id,
        hg.hk_group_id,
        now() as load_dt,
        's3' as load_src
    from stv2023121113__STAGING.group_log as gl
        left join stv2023121113__DWH.h_users as hu on gl.user_id = hu.user_id
        left join stv2023121113__DWH.h_groups as hg on gl.group_id = hg.group_id
    where hash(hu.hk_user_id, hg.hk_group_id) not in (select hk_l_user_group_activity from stv2023121113__DWH.l_user_group_activity);


    ------------------------------
    ---AUTH HISTORY SATELLITE
    ------------------------------

    create table stv2023121113__DWH.s_auth_history
    (
        hk_l_user_group_activity bigint not null CONSTRAINT fk_l_user_group_activity REFERENCES stv2023121113__DWH.l_user_group_activity (hk_l_user_group_activity),
        user_id_from integer,
        event varchar(100),
        event_dt datetime,
        load_dt datetime,
        load_scr varchar(20)
    )
    order by load_dt
    SEGMENTED BY hk_l_user_group_activity all nodes
    PARTITION BY load_dt::date
    GROUP BY calendar_hierarchy_day(load_dt::date, 3, 2);


    INSERT INTO stv2023121113__DWH.s_auth_history(hk_l_user_group_activity, user_id_from,event,event_dt,load_dt,load_scr)
    select distinct
        luga.hk_l_user_group_activity
        , gl.user_id_from
        ,gl.event
        , gl.datetime
        ,now() as load_dt
        ,'s3' as load_src
    from stv2023121113__STAGING.group_log as gl
    left join stv2023121113__DWH.h_groups as hg on gl.group_id = hg.group_id
    left join stv2023121113__DWH.h_users as hu on gl.user_id = hu.user_id
    left join stv2023121113__DWH.l_user_group_activity as luga on (hg.hk_group_id = luga.hk_group_id) and (hu.hk_user_id = luga.hk_user_id)
    where luga.hk_l_user_group_activity not in (select hk_l_user_group_activity from stv2023121113__DWH.s_auth_history)
    and gl.event = 'add' or gl.event = 'leave';

        """)
    for i in ['h_users', 'h_groups', 'l_user_group_activity', 's_auth_history']:
        sql = f"select count(*) from stv2023121113__DWH.{i}"
        cur.execute(sql)
        result = cur.fetchall()[0][0]
        logging.info(f'fetched result in DB - {result}')
    cur.execute('COMMIT;')
    cur.close()


default_args = {
    'owner': 'Airflow',
    'schedule_interval':'@once',           # sheduled or not
    'retries': 1,                          # the number of retries that should be performed before failing the task
    'retry_delay': timedelta(minutes=5),   # delay between retries
    'depends_on_past': False,
    'catchup':False
}

with DAG(
        'load_to_Vertica_DDS',                 # name
        default_args=default_args,         # connect args
        schedule_interval='0/15 * * * *',  # interval
        start_date=datetime(2021, 1, 1),   # start calc
        catchup=False,                     # used in  the first launch, from date in the past until now. Usually = off
        tags=['sprint6', 'example'],
) as dag:

    # create DAG logic (sequence/order)
    t1 = DummyOperator(task_id="start")
    t2 = PythonOperator(task_id="create_tables_and_load_data", python_callable=execute_vertica, dag=dag)
    t4 = DummyOperator(task_id="end")

    t1 >> t2 >> t4
