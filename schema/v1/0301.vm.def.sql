-- =============================================================================
-- VM TABLES
-- =============================================================================
CREATE TABLE core.vms (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    hypervisor_host_id int REFERENCES core.hypervisor_hosts(id),
    compute_pool_id int REFERENCES core.compute_pools(id),
    template_id int references core.templates(id),
    power_state_id int REFERENCES core.power_states(id),
    cost_center_id int REFERENCES core.cost_centers(id),
    team_id int REFERENCES core.teams(id),
    project_id int references core.projects(id),
    environment_id int REFERENCES core.environments(id),
    service_id int references core.services(id),
    arch_id int NULL REFERENCES core.cpu_archs(id),
    os_id int NULL REFERENCES core.operating_systems(id),
    vm_status int references core.vm_status_types(id),
    vm_name varchar(255) NOT NULL UNIQUE,
    ipv4 varchar(55) NOT NULL UNIQUE,
    shortname varchar(255) unique,
    fqdn varchar(255) unique,
    refname varchar(255) unique,
    vm_uuid varchar(55) NULL UNIQUE,
    cpus int NULL,
    memory_mb int8 NULL,
    storage_total_gb int8 NULL,
    has_backup boolean,
    has_dr boolean,
    kernel varchar(255),
    metadata jsonb NULL
);

CREATE TABLE core.vm_disks (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vm_id int NOT NULL REFERENCES core.vms(id),
    datastore_id int REFERENCES core.datastores(id),
    disk_format_id int NULL REFERENCES core.disk_formats(id),
    label varchar(55) NULL,
    size_gb int8 NOT NULL,
    disk_path varchar(512) NULL,
    boot_disk bool NOT NULL DEFAULT false
);

CREATE TABLE core.vm_mounts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vm_id int not null references core.vms(id),
    mountpoint varchar not null,
    source varchar not null,
    fstype  varchar(55) not null,
    opts varchar[],
    status varchar(55),
    in_fstab boolean,
    size bigint,
    used_last_seen bigint,
    used_pct numeric,
    CONSTRAINT uq_vm_mounts UNIQUE (vm_id, mountpoint)
);

CREATE TABLE core.vm_nics (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vm_id int NOT NULL REFERENCES core.vms(id),
    network_id int REFERENCES core.networks(id),
    adapter_type_id int NULL REFERENCES core.adapter_types(id),
    mac_address varchar(55) NULL,
    ipv4 varchar(55) NULL,
    ipv6 varchar(55) NULL,
    connected bool NOT NULL DEFAULT true
);

CREATE TABLE core.vm_snapshots (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vm_id int NOT NULL REFERENCES core.vms(id),
    parent_id int NULL REFERENCES core.vm_snapshots(id),
    snapshot_name varchar(255) NOT NULL,
    description text NULL,
    size_gb int8 NULL,
    quiesced bool NOT NULL DEFAULT false,
    platform_ref varchar(255) NULL
);