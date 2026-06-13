-- =============================================================================
-- SOFTWARE TABLES
-- =============================================================================
CREATE TABLE software_licenses (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name varchar not null unique,
    shortname text unique
);

CREATE TABLE software_packages (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fullname varchar(511) not null unique,
    name varchar(255),
    version varchar(255),
    arch varchar(15),
    license_id int references software_licenses(id),
    vendor int references vendors(id)
);

create table vm_packages (
    vm_id int references vms(id) on delete cascade,
    package_id bigint references software_packages(id) on delete cascade,
    constraint pk_vm_pkgs primary key (vm_id, package_id)
);