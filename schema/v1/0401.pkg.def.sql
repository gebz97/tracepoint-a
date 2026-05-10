-- =============================================================================
-- SOFTWARE TABLES
-- =============================================================================
CREATE TABLE core.software_licenses (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name varchar not null unique,
    shortname text unique
);

CREATE TABLE core.software_packages (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fullname varchar(511) not null unique,
    name varchar(255),
    version varchar(255),
    arch varchar(15),
    license_id int references core.software_licenses(id),
    vendor int references core.vendors(id)
);

create table core.vm_packages (
    vm_id int references core.vms(id),
    package_id bigint references core.software_packages(id),
    constraint pk_vm_pkgs primary key (vm_id, package_id)
);