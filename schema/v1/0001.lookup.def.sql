-- =============================================================================
-- LOOKUP TABLES
-- =============================================================================
CREATE TABLE core.hypervisor_types (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name varchar(55) NOT NULL UNIQUE
);

CREATE TABLE core.platform_vendors (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name varchar(55) NOT NULL UNIQUE
);

CREATE TABLE core.datastore_types (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name varchar(55) NOT NULL UNIQUE
);

CREATE TABLE core.network_types (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name varchar(55) NOT NULL UNIQUE
);

CREATE TABLE core.disk_formats (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name varchar(55) NOT NULL UNIQUE
);

CREATE TABLE core.adapter_types (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name varchar(55) NOT NULL UNIQUE
);

CREATE TABLE core.cluster_types (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name varchar(55) NOT NULL UNIQUE
);

CREATE TABLE core.cpu_archs (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name varchar(55) NOT NULL UNIQUE
);

CREATE TABLE core.power_states (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name varchar(55) NOT NULL UNIQUE
);

CREATE TABLE core.host_statuses (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name varchar(55) NOT NULL UNIQUE
);

CREATE TABLE core.environments (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name varchar(55) NOT NULL UNIQUE,
    abbr varchar(1) NOT NULL UNIQUE,
    description text
);

CREATE TABLE core.vm_function_types (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name varchar(55) NOT NULL UNIQUE,
    abbr varchar(3) NOT NULL UNIQUE,
    description text
);

CREATE TABLE core.vm_special_contexts (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name varchar(55) NOT NULL UNIQUE,
    abbr varchar(2) NOT NULL UNIQUE,
    description text
);

CREATE TABLE core.operating_systems (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fullname varchar(255) not null unique,
    name varchar(255),
    version varchar(255),
    major_version varchar(55),
    minor_version varchar(55),
    vendor varchar(255)
);

create table core.vm_status_types (
    id int generated always as identity primary key,
    name varchar(55),
    abbr varchar(1)
);