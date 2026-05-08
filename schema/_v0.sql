drop schema core cascade;

create schema core;

create table core.os_versions (
    id int generated always as identity primary key,
    os_version varchar(255) not null unique,
    vendor varchar(255),
    release_date date,
    eol date,
    eos date,
    eosl date
);

create table core.environments (
    id int generated always as identity primary key,
    shortname varchar(55) not null unique,
    description text
);

create table core.severity_types (
    id int generated always as identity primary key,
    shortname varchar(55) not null unique,
    description text
);

create table core.services (
    id int generated always as identity primary key,
    shortname varchar(255) not null unique,
    severity_id int references core.severity_types(id)
);

create table core.vms (
    id int generated always as identity primary key,
    vm_name varchar(255) not null unique,
    ipv4 varchar(55) not null unique,
    environment_id int references core.environments(id),
    service_id int references core.services(id),
    os int references core.os_versions(id),
    memory_mb int8 null,
    storage_total_gb int8 null,
    metadata jsonb null
);

create table core.software_licenses (
    id int generated always as identity primary key,
    license_name varchar(255),
    shortname varchar(55)
);

create table core.software_packages (
    id bigint generated always as identity primary key,
    package_name varchar(255) not null,
    package_version varchar(255) not null,
    arch varchar(55) not null,
    format varchar(55) not null,
    summary text,
    description text,
    url text,
    license int references core.software_licenses(id),
    keywords varchar(55)[],
    constraint unique_pkg_name_version_arch unique(package_name, package_version, arch)
);

create table core.vm_packages (
    vm_id int references core.vms(id),
    package_id bigint references core.software_packages(id),
    constraint pk_vm_package primary key (vm_id,package_id)
);

create table core.daemons (
    id bigint generated always as identity primary key,
    daemon_name varchar(255) not null,
    vm_id int not null references core.vms(id)
);


-- VIEWS ----
create or replace view core.vw_vms (

);