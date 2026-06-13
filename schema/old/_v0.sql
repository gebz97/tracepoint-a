drop schema core cascade;

create schema core;

create table os_versions (
    id int generated always as identity primary key,
    os_version varchar(255) not null unique,
    vendor varchar(255),
    release_date date,
    eol date,
    eos date,
    eosl date
);

create table environments (
    id int generated always as identity primary key,
    shortname varchar(55) not null unique,
    description text
);

create table severity_types (
    id int generated always as identity primary key,
    shortname varchar(55) not null unique,
    description text
);

create table services (
    id int generated always as identity primary key,
    shortname varchar(255) not null unique,
    severity_id int references severity_types(id)
);

create table vms (
    id int generated always as identity primary key,
    vm_name varchar(255) not null unique,
    ipv4 varchar(55) not null unique,
    environment_id int references environments(id),
    service_id int references services(id),
    os int references os_versions(id),
    memory_mb int8 null,
    storage_total_gb int8 null,
    metadata jsonb null
);

create table software_licenses (
    id int generated always as identity primary key,
    license_name varchar(255),
    shortname varchar(55)
);

create table software_packages (
    id bigint generated always as identity primary key,
    package_name varchar(255) not null,
    package_version varchar(255) not null,
    arch varchar(55) not null,
    format varchar(55) not null,
    summary text,
    description text,
    url text,
    license int references software_licenses(id),
    keywords varchar(55)[],
    constraint unique_pkg_name_version_arch unique(package_name, package_version, arch)
);

create table vm_packages (
    vm_id int references vms(id),
    package_id bigint references software_packages(id),
    constraint pk_vm_package primary key (vm_id,package_id)
);

create table daemons (
    id bigint generated always as identity primary key,
    daemon_name varchar(255) not null,
    vm_id int not null references vms(id)
);


-- VIEWS ----
create or replace view vw_vms (

);