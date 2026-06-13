-- =============================================================================
-- LOOKUP TABLES
-- =============================================================================
CREATE TABLE hypervisor_types (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name varchar(55) NOT NULL UNIQUE
);

CREATE TABLE platform_vendors (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name varchar(55) NOT NULL UNIQUE
);

CREATE TABLE datastore_types (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name varchar(55) NOT NULL UNIQUE
);

CREATE TABLE network_types (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name varchar(55) NOT NULL UNIQUE
);

CREATE TABLE disk_formats (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name varchar(55) NOT NULL UNIQUE
);

CREATE TABLE adapter_types (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name varchar(55) NOT NULL UNIQUE
);

CREATE TABLE cluster_types (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name varchar(55) NOT NULL UNIQUE
);

CREATE TABLE cpu_archs (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name varchar(55) NOT NULL UNIQUE
);

CREATE TABLE power_states (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name varchar(55) NOT NULL UNIQUE
);

CREATE TABLE host_statuses (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name varchar(55) NOT NULL UNIQUE
);

CREATE TABLE environments (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name varchar(55) NOT NULL UNIQUE,
    abbr varchar(1) NOT NULL UNIQUE,
    description text
);

CREATE TABLE vm_function_types (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name varchar(55) NOT NULL UNIQUE,
    abbr varchar(3) NOT NULL UNIQUE,
    description text
);

CREATE TABLE vm_special_contexts (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name varchar(55) NOT NULL UNIQUE,
    abbr varchar(2) NOT NULL UNIQUE,
    description text
);

CREATE TABLE operating_systems (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fullname varchar(255) not null unique,
    name varchar(255),
    version varchar(255),
    major_version varchar(55),
    minor_version varchar(55),
    vendor varchar(255)
);

create table vm_status_types (
    id int generated always as identity primary key,
    name varchar(55),
    abbr varchar(1)
);