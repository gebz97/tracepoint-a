-- =============================================================================
-- INFRA TABLES
-- =============================================================================

CREATE TABLE core.datacenters (
    id                  int             GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    datacenter_name     varchar(255)    NOT NULL UNIQUE,
    location            varchar(255)    NULL,
    description         text            NULL,
    metadata            jsonb           NULL,
    created_at          timestamp       NOT NULL DEFAULT now(),
    updated_at          timestamp       NOT NULL DEFAULT now()
);

CREATE TABLE core.clusters (
    id                  int             GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    datacenter_id       int             NOT NULL REFERENCES core.datacenters(id),
    cluster_type_id     int             NULL     REFERENCES core.cluster_types(id),
    cluster_name        varchar(255)    NOT NULL,
    high_availability   bool            NOT NULL DEFAULT false,
    load_balancing      bool            NOT NULL DEFAULT false,
    description         text            NULL,
    features            jsonb           NULL,
    created_at          timestamp       NOT NULL DEFAULT now(),
    updated_at          timestamp       NOT NULL DEFAULT now(),
    CONSTRAINT clusters_unique UNIQUE (datacenter_id, cluster_name)
);

CREATE TABLE core.hypervisor_hosts (
    id                  int             GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cluster_id          int             NOT NULL REFERENCES core.clusters(id),
    hypervisor_type_id  int             NOT NULL REFERENCES core.hypervisor_types(id),
    platform_vendor_id  int             NULL     REFERENCES core.platform_vendors(id),
    status_id           int             NOT NULL REFERENCES core.host_statuses(id),
    hostname            varchar(255)    NOT NULL UNIQUE,
    ipv4                varchar(55)     NOT NULL UNIQUE,
    ipmi_ip             varchar(55)     NULL,
    hypervisor_version  varchar(55)     NULL,
    platform_ref        varchar(255)    NULL,
    manufacturer        varchar(255)    NULL,
    model               varchar(255)    NULL,
    serial_number       varchar(255)    NULL,
    cpu_model           varchar(255)    NULL,
    cpu_sockets         int             NULL,
    cpu_cores           int             NULL,
    memory_mb           int8            NULL,
    maintenance_mode    bool            NOT NULL DEFAULT false,
    metadata            jsonb           NULL,
    created_at          timestamp       NOT NULL DEFAULT now(),
    updated_at          timestamp       NOT NULL DEFAULT now()
);

CREATE TABLE core.datastores (
    id                  int             GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    datacenter_id       int             NOT NULL REFERENCES core.datacenters(id),
    datastore_type_id   int             NOT NULL REFERENCES core.datastore_types(id),
    datastore_name      varchar(255)    NOT NULL UNIQUE,
    ds_path             varchar(512)    NULL,
    total_gb            int8            NULL,
    used_gb             int8            NULL,
    free_gb             int8            GENERATED ALWAYS AS (total_gb - used_gb) STORED,
    thin_provisioned    bool            NOT NULL DEFAULT true,
    replication_enabled bool            NOT NULL DEFAULT false,
    platform_ref        varchar(255)    NULL,
    metadata            jsonb           NULL,
    created_at          timestamp       NOT NULL DEFAULT now(),
    updated_at          timestamp       NOT NULL DEFAULT now()
);

CREATE TABLE core.datastore_hosts (
    datastore_id        int             NOT NULL REFERENCES core.datastores(id),
    host_id             int             NOT NULL REFERENCES core.hypervisor_hosts(id),
    mounted_at          timestamp       NOT NULL DEFAULT now(),
    read_only           bool            NOT NULL DEFAULT false,
    PRIMARY KEY (datastore_id, host_id)
);

CREATE TABLE core.networks (
    id                  int             GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    network_type_id     int             NULL     REFERENCES core.network_types(id),
    network_name        varchar(255)    NOT NULL,
    vlan_id             int             NULL,
    virtual_switch      varchar(255)    NULL,
    cidr                varchar(55)     NULL,
    gateway             varchar(55)     NULL,
    dns_servers         text[]          NULL,
    platform_ref        varchar(255)    NULL,
    metadata            jsonb           NULL,
    created_at          timestamp       NOT NULL DEFAULT now(),
    updated_at          timestamp       NOT NULL DEFAULT now(),
    CONSTRAINT networks_unique UNIQUE (network_name, vlan_id)
);

CREATE TABLE core.network_hosts (
    network_id          int             NOT NULL REFERENCES core.networks(id),
    host_id             int             NOT NULL REFERENCES core.hypervisor_hosts(id),
    PRIMARY KEY (network_id, host_id)
);

CREATE TABLE core.compute_pools (
    id                  int             GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cluster_id          int             NOT NULL REFERENCES core.clusters(id),
    parent_id           int             NULL     REFERENCES core.compute_pools(id),
    pool_name           varchar(255)    NOT NULL,
    cpu_shares          int             NULL,
    cpu_limit_mhz       int             NULL,
    mem_shares          int             NULL,
    mem_limit_mb        int8            NULL,
    platform_ref        varchar(255)    NULL,
    created_at          timestamp       NOT NULL DEFAULT now(),
    updated_at          timestamp       NOT NULL DEFAULT now(),
    CONSTRAINT compute_pools_unique UNIQUE (cluster_id, pool_name)
);

CREATE TABLE core.templates (
    id                  int             GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    datastore_id        int             NULL REFERENCES core.datastores(id),
    arch_id             int             NULL REFERENCES core.cpu_archs(id),
    template_name       varchar(255)    NOT NULL UNIQUE,
    distribution        varchar(255)    NULL,
    os_version          varchar(255)    NULL,
    platform_ref        varchar(255)    NULL,
    notes               text            NULL,
    created_at          timestamp       NOT NULL DEFAULT now(),
    updated_at          timestamp       NOT NULL DEFAULT now()
);
