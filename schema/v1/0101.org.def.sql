-- =============================================================================
-- ORGANIZATIONAL
-- =============================================================================
CREATE TABLE core.teams (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    team_name varchar(255) NOT NULL UNIQUE,
    description text NULL,
    email varchar(255) NULL,
    metadata jsonb NULL
);

CREATE TABLE core.contacts (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name varchar(255) NOT NULL,
    email varchar(255) NOT NULL UNIQUE,
    metadata jsonb NULL
);

-- team members (many-to-many, a contact can be in multiple teams)
CREATE TABLE core.team_contacts (
    team_id int NOT NULL REFERENCES core.teams(id),
    contact_id int NOT NULL REFERENCES core.contacts(id),
    role varchar(55) NULL,
    PRIMARY KEY (team_id, contact_id)
);

CREATE TABLE core.services (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    team_id int NOT NULL REFERENCES core.teams(id),
    service_name varchar(255) NOT NULL UNIQUE,
    description text NULL,
    metadata jsonb NULL
);

CREATE TABLE core.cost_centers (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cost_center_code varchar(55) NOT NULL UNIQUE,
    cost_center_name varchar(255) NOT NULL,
    description text NULL
);

CREATE TABLE core.projects (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    team_id int NOT NULL REFERENCES core.teams(id),
    cost_center_id int NULL REFERENCES core.cost_centers(id),
    project_name varchar(255) NOT NULL UNIQUE,
    description text NULL,
    start_date date NULL,
    end_date date NULL,
    metadata jsonb NULL
);

create table core.vendors (
    id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name varchar(255) not null unique,
    country varchar(255),
    description text,
    primary_contact text
);