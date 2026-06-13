-- =============================================================================
-- INFRA TABLES
-- =============================================================================
CREATE TABLE datacenters (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    datacenter_name varchar(255) NOT NULL UNIQUE,
    location varchar(255) NULL,
    description text NULL,
    metadata jsonb NULL
);

CREATE TABLE clusters (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    datacenter_id int NOT NULL REFERENCES datacenters(id),
    cluster_type_id int NULL REFERENCES cluster_types(id),
    cluster_name varchar(255) NOT NULL,
    high_availability bool NOT NULL DEFAULT false,
    load_balancing bool NOT NULL DEFAULT false,
    description text NULL,
    features jsonb NULL,
    CONSTRAINT clusters_unique UNIQUE (datacenter_id, cluster_name)
);

CREATE TABLE hypervisor_hosts (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cluster_id int NOT NULL REFERENCES clusters(id),
    hypervisor_type_id int NOT NULL REFERENCES hypervisor_types(id),
    platform_vendor_id int NULL REFERENCES platform_vendors(id),
    status_id int NOT NULL REFERENCES host_statuses(id),
    hostname varchar(255) NOT NULL UNIQUE,
    ipv4 varchar(55) NOT NULL UNIQUE,
    ipmi_ip varchar(55) NULL,
    hypervisor_version varchar(55) NULL,
    platform_ref varchar(255) NULL,
    manufacturer varchar(255) NULL,
    model varchar(255) NULL,
    serial_number varchar(255) NULL,
    cpu_model varchar(255) NULL,
    cpu_sockets int NULL,
    cpu_cores int NULL,
    memory_mb int8 NULL,
    maintenance_mode bool NOT NULL DEFAULT false,
    metadata jsonb NULL
);

CREATE TABLE datastores (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    datacenter_id int NOT NULL REFERENCES datacenters(id),
    datastore_type_id int NOT NULL REFERENCES datastore_types(id),
    datastore_name varchar(255) NOT NULL UNIQUE,
    ds_path varchar(512) NULL,
    total_gb int8 NULL,
    used_gb int8 NULL,
    free_gb int8 GENERATED ALWAYS AS (total_gb - used_gb) STORED,
    thin_provisioned bool NOT NULL DEFAULT true,
    replication_enabled bool NOT NULL DEFAULT false,
    platform_ref varchar(255) NULL,
    metadata jsonb NULL
);

CREATE TABLE datastore_hosts (
    datastore_id int NOT NULL REFERENCES datastores(id),
    host_id int NOT NULL REFERENCES hypervisor_hosts(id),
    mounted_at timestamp NOT NULL DEFAULT now(),
    read_only bool NOT NULL DEFAULT false,
    PRIMARY KEY (datastore_id, host_id)
);

CREATE TABLE networks (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    network_type_id int NULL REFERENCES network_types(id),
    network_name varchar(255) NOT NULL,
    vlan_id int NULL,
    virtual_switch varchar(255) NULL,
    cidr varchar(55) NULL,
    gateway varchar(55) NULL,
    dns_servers text [] NULL,
    platform_ref varchar(255) NULL,
    metadata jsonb NULL,
    CONSTRAINT networks_unique UNIQUE (network_name, vlan_id)
);

CREATE TABLE network_hosts (
    network_id int NOT NULL REFERENCES networks(id),
    host_id int NOT NULL REFERENCES hypervisor_hosts(id),
    PRIMARY KEY (network_id, host_id)
);

CREATE TABLE compute_pools (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cluster_id int NOT NULL REFERENCES clusters(id),
    parent_id int NULL REFERENCES compute_pools(id),
    pool_name varchar(255) NOT NULL,
    cpu_shares int NULL,
    cpu_limit_mhz int NULL,
    mem_shares int NULL,
    mem_limit_mb int8 NULL,
    platform_ref varchar(255) NULL,
    CONSTRAINT compute_pools_unique UNIQUE (cluster_id, pool_name)
);

CREATE TABLE templates (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    datastore_id int NULL REFERENCES datastores(id),
    arch_id int NULL REFERENCES cpu_archs(id),
    template_name varchar(255) NOT NULL UNIQUE,
    distribution varchar(255) NULL,
    os_version varchar(255) NULL,
    platform_ref varchar(255) NULL,
    notes text NULL
);