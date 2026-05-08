-- =============================================================================
-- ORGANIZATIONAL
-- =============================================================================

create table public.teams (
    id bigint generated always as identity primary key,
    name varchar(255) not null unique,
    description text,
    email varchar(255),
    metadata jsonb,
    created_at timestamp not null default now(),
    updated_at timestamp not null default now()
);

create table public.contacts (
    id bigint generated always as identity primary key,
    full_name varchar(255) not null,
    email varchar(255) unique,
    metadata jsonb,
    created_at timestamp not null default now(),
    updated_at timestamp not null default now()
);

create table public.team_contacts (
    team_id bigint not null references public.teams(id) on
delete
	cascade,
	contact_id bigint not null references public.contacts(id) on
	delete
		cascade,
		role varchar(64),
		primary key (team_id,
		contact_id)
);

create table public.cost_centers (
    id bigint generated always as identity primary key,
    code varchar(64) not null unique,
    name varchar(255) not null,
    description text,
    metadata jsonb,
    created_at timestamp not null default now(),
    updated_at timestamp not null default now()
);

create table public.projects (
    id bigint generated always as identity primary key,
    team_id bigint references public.teams(id),
    cost_center_id bigint references public.cost_centers(id),

    name varchar(255) not null unique,
    description text,

    start_date date,
    end_date date,

    metadata jsonb,

    created_at timestamp not null default now(),
    updated_at timestamp not null default now()
);

create table public.services (
    id bigint generated always as identity primary key,
    team_id bigint references public.teams(id),

    name varchar(255) not null unique,
    description text,

    metadata jsonb,

    created_at timestamp not null default now(),
    updated_at timestamp not null default now()
);
-- =============================================================================
-- INFRASTRUCTURE
-- =============================================================================

create table public.datacenters (
    id bigint generated always as identity primary key,

    name varchar(255) not null unique,
    location varchar(255),
    description text,

    metadata jsonb,

    created_at timestamp not null default now(),
    updated_at timestamp not null default now()
);

create table public.clusters (
    id bigint generated always as identity primary key,

    datacenter_id bigint not null
                        references public.datacenters(id),

    name varchar(255) not null,

    cluster_type varchar(64),
    hypervisor_type varchar(64),

    high_availability boolean not null default false,
    load_balancing boolean not null default false,

    description text,
    features jsonb,
    metadata jsonb,

    created_at timestamp not null default now(),
    updated_at timestamp not null default now(),

    unique(datacenter_id,
name)
);

create table public.hypervisor_hosts (
    id bigint generated always as identity primary key,

    cluster_id bigint not null
                        references public.clusters(id),

    hostname varchar(255) not null unique,
    ipv4 varchar(55) not null unique,

    ipmi_ip varchar(55),

    hypervisor_type varchar(64) not null,
    platform_vendor varchar(64),

    status varchar(64) not null default 'online',

    hypervisor_version varchar(64),

    platform_ref varchar(255),

    manufacturer varchar(255),
    model varchar(255),
    serial_number varchar(255),

    cpu_arch varchar(64),
    cpu_model varchar(255),

    cpu_sockets integer,
    cpu_cores integer,

    memory_mb bigint,

    maintenance_mode boolean not null default false,

    tags text[],
    metadata jsonb,

    created_at timestamp not null default now(),
    updated_at timestamp not null default now()
);

create table public.datastores (
    id bigint generated always as identity primary key,

    datacenter_id bigint not null
                            references public.datacenters(id),

    name varchar(255) not null unique,

    datastore_type varchar(64) not null,

    path varchar(512),

    total_gb bigint,
    used_gb bigint,

    free_gb bigint generated always as (
                                total_gb - used_gb
                            ) stored,

    thin_provisioned boolean not null default true,
    replication_enabled boolean not null default false,

    platform_ref varchar(255),

    tags text[],
    metadata jsonb,

    created_at timestamp not null default now(),
    updated_at timestamp not null default now()
);

create table public.datastore_hosts (
    datastore_id bigint not null
                        references public.datastores(id)
                        on
delete
	cascade,
	host_id bigint not null
                        references public.hypervisor_hosts(id)
                        on
	delete
		cascade,
		mounted_at timestamp not null default now(),
		read_only boolean not null default false,
		primary key(datastore_id,
		host_id)
);

create table public.networks (
    id bigint generated always as identity primary key,

    name varchar(255) not null,

    network_type varchar(64),

    vlan_id integer,

    subnet varchar(55),
    gateway varchar(55),

    virtual_switch varchar(255),

    dns_servers varchar(55)[],

    platform_ref varchar(255),

    tags text[],
    metadata jsonb,

    created_at timestamp not null default now(),
    updated_at timestamp not null default now(),

    unique(name,
vlan_id)
);

create table public.network_hosts (
    network_id bigint not null
                        references public.networks(id)
                        on
delete
	cascade,
	host_id bigint not null
                        references public.hypervisor_hosts(id)
                        on
	delete
		cascade,
		primary key(network_id,
		host_id)
);

create table public.compute_pools (
    id bigint generated always as identity primary key,

    cluster_id bigint not null
                        references public.clusters(id),

    parent_id bigint
                        references public.compute_pools(id),

    name varchar(255) not null,

    cpu_shares integer,
    cpu_limit_mhz integer,

    mem_shares integer,
    mem_limit_mb bigint,

    platform_ref varchar(255),

    metadata jsonb,

    created_at timestamp not null default now(),
    updated_at timestamp not null default now(),

    unique(cluster_id,
name)
);

create table public.templates (
    id bigint generated always as identity primary key,

    datastore_id bigint
                        references public.datastores(id),

    name varchar(255) not null unique,

    distribution varchar(255),
    os_version varchar(255),

    cpu_arch varchar(64),

    platform_ref varchar(255),

    notes text,

    tags text[],
    metadata jsonb,

    created_at timestamp not null default now(),
    updated_at timestamp not null default now()
);

create table public.vms (
    id bigint generated always as identity primary key,

    hypervisor_host_id bigint
                            references public.hypervisor_hosts(id),

    compute_pool_id bigint
                            references public.compute_pools(id),

    template_id bigint
                            references public.templates(id),

    service_id bigint
                            references public.services(id),

    team_id bigint
                            references public.teams(id),

    project_id bigint
                            references public.projects(id),

    cost_center_id bigint
                            references public.cost_centers(id),

    vm_name varchar(255) not null unique,

    ipv4 varchar(55) not null unique,

    power_state varchar(64) default 'unknown',
    environment varchar(64),

    service_tag varchar(64),

    distribution varchar(255),
    os_version varchar(255),
    os_major integer,

    cpu_arch varchar(64),

    cpus integer,
    memory_mb bigint,

    storage_total_gb bigint,

    platform_ref varchar(255),

    tags text[],
    metadata jsonb,

    created_at timestamp not null default now(),
    updated_at timestamp not null default now()
);

create table public.vm_disks (
    id bigint generated always as identity primary key,

    vm_id bigint not null
                        references public.vms(id)
                        on
delete
	cascade,
	datastore_id bigint
                        references public.datastores(id),
	label varchar(64),
	disk_format varchar(64),
	size_gb bigint not null,
	disk_path varchar(512),
	boot_disk boolean not null default false,
	metadata jsonb,
	created_at timestamp not null default now(),
	updated_at timestamp not null default now()
);

create table public.vm_nics (
    id bigint generated always as identity primary key,

    vm_id bigint not null
                        references public.vms(id)
                        on
delete
	cascade,
	network_id bigint
                        references public.networks(id),
	adapter_type varchar(64),
	mac_address macaddr,
	ipv4 varchar(55),
	ipv6 varchar(55),
	connected boolean not null default true,
	metadata jsonb,
	created_at timestamp not null default now(),
	updated_at timestamp not null default now()
);

create table public.vm_snapshots (
    id bigint generated always as identity primary key,

    vm_id bigint not null
                        references public.vms(id)
                        on
delete
	cascade,
	parent_id bigint
                        references public.vm_snapshots(id),
	name varchar(255) not null,
	description text,
	size_gb bigint,
	quiesced boolean not null default false,
	platform_ref varchar(255),
	metadata jsonb,
	created_at timestamp not null default now()
);
-- =============================================================================
-- INDEXES
-- =============================================================================

create index idx_clusters_dc
    on
public.clusters(datacenter_id);

create index idx_hosts_cluster
    on
public.hypervisor_hosts(cluster_id);

create index idx_hosts_type
    on
public.hypervisor_hosts(hypervisor_type);

create index idx_hosts_status
    on
public.hypervisor_hosts(status);

create index idx_hosts_metadata
    on
public.hypervisor_hosts
	using gin(metadata);

create index idx_vms_host
    on
public.vms(hypervisor_host_id);

create index idx_vms_environment
    on
public.vms(environment);

create index idx_vms_power_state
    on
public.vms(power_state);

create index idx_vms_metadata
    on
public.vms
	using gin(metadata);

create index idx_networks_type
    on
public.networks(network_type);

create index idx_vm_disks_vm
    on
public.vm_disks(vm_id);

create index idx_vm_nics_vm
    on
public.vm_nics(vm_id);

create index idx_vm_snapshots_vm
    on
public.vm_snapshots(vm_id);