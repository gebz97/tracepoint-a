-- =============================================================================
-- INDEXES
-- =============================================================================
CREATE INDEX idx_clusters_datacenter ON core.clusters USING btree (datacenter_id);

CREATE INDEX idx_clusters_type ON core.clusters USING btree (cluster_type_id);

CREATE INDEX idx_hosts_cluster ON core.hypervisor_hosts USING btree (cluster_id);

CREATE INDEX idx_hosts_status ON core.hypervisor_hosts USING btree (status_id);

CREATE INDEX idx_hosts_type ON core.hypervisor_hosts USING btree (hypervisor_type_id);

CREATE INDEX idx_hosts_vendor ON core.hypervisor_hosts USING btree (platform_vendor_id);

CREATE INDEX idx_hosts_metadata ON core.hypervisor_hosts USING gin (metadata);

CREATE INDEX idx_datastores_datacenter ON core.datastores USING btree (datacenter_id);

CREATE INDEX idx_datastores_type ON core.datastores USING btree (datastore_type_id);

CREATE INDEX idx_networks_type ON core.networks USING btree (network_type_id);

CREATE INDEX idx_compute_pools_cluster ON core.compute_pools USING btree (cluster_id);

CREATE INDEX idx_compute_pools_parent ON core.compute_pools USING btree (parent_id);

CREATE INDEX idx_vms_host ON core.vms USING btree (hypervisor_host_id);

CREATE INDEX idx_vms_pool ON core.vms USING btree (compute_pool_id);

CREATE INDEX idx_vms_power_state ON core.vms USING btree (power_state_id);

CREATE INDEX idx_vms_environment ON core.vms USING btree (environment_id);

CREATE INDEX idx_vms_metadata ON core.vms USING gin (metadata);

CREATE INDEX idx_vm_disks_vm ON core.vm_disks USING btree (vm_id);

CREATE INDEX idx_vm_disks_datastore ON core.vm_disks USING btree (datastore_id);

CREATE INDEX idx_vm_disks_format ON core.vm_disks USING btree (disk_format_id);

CREATE INDEX idx_vm_nics_vm ON core.vm_nics USING btree (vm_id);

CREATE INDEX idx_vm_nics_network ON core.vm_nics USING btree (network_id);

CREATE INDEX idx_snapshots_vm ON core.vm_snapshots USING btree (vm_id);

CREATE INDEX idx_snapshots_parent ON core.vm_snapshots USING btree (parent_id);