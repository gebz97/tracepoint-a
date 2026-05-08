-- =============================================================================
-- SOFTWARE TABLES
-- =============================================================================
CREATE TABLE core.software_licenses (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name varchar(255) not null unique,
    shortname varchar(55) unique
);

CREATE TABLE core.software_packages (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fullname varchar(255) not null unique,
    name varchar(55),
    version varchar(55),
    arch varchar(15),
    license_id int references core.software_licenses(id),
    vendor int references core.vendors(id),
    created_at timestamp NOT NULL DEFAULT now(),
    updated_at timestamp NOT NULL DEFAULT now()
);

create table core.vm_packages (
    vm_id int references core.vms(id),
    package_id bigint references core.software_packages(id),
    created_at timestamp NOT NULL DEFAULT now(),
    updated_at timestamp NOT NULL DEFAULT now(),
    constraint pk_vm_pkgs primary key (vm_id, package_id)
);