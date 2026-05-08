CREATE TABLE core.vm_groups (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vm_id INT NOT NULL REFERENCES core.vms(id) ON DELETE CASCADE,
    name VARCHAR(55) NOT NULL,
    gid INT,
    description TEXT,
    UNIQUE(vm_id, name)
);

CREATE TABLE core.vm_users (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vm_id INT NOT NULL REFERENCES core.vms(id) ON DELETE CASCADE,
    name VARCHAR(55) NOT NULL,
    uid INT NOT NULL,
    pgroup VARCHAR(55) NOT NULL,
    groups VARCHAR(55)[] NOT NULL,
    gid INT,
    gids INT[],
    has_sudo BOOLEAN,
    description TEXT,
    UNIQUE(vm_id, name),
    UNIQUE(vm_id, uid)
);