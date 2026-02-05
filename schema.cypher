// Vedic Mind (Chitta) - Tripartite Graph Schema
// Context (Buddhi) - Goals/States with vector embeddings
// Moment (Chitta) - Time-based episode hubs
// Sensor (Indriyas) - Keywords/entities
// Action (Karma) - Solutions/responses

// Constraints for uniqueness
CREATE CONSTRAINT context_id IF NOT EXISTS FOR (c:Context) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT moment_id IF NOT EXISTS FOR (m:Moment) REQUIRE m.id IS UNIQUE;
CREATE CONSTRAINT sensor_id IF NOT EXISTS FOR (s:Sensor) REQUIRE s.id IS UNIQUE;
CREATE CONSTRAINT action_id IF NOT EXISTS FOR (a:Action) REQUIRE a.id IS UNIQUE;

// Indexes for fast lookup
CREATE INDEX context_name IF NOT EXISTS FOR (c:Context) ON (c.name);
CREATE INDEX sensor_value IF NOT EXISTS FOR (s:Sensor) ON (s.value);
CREATE INDEX moment_timestamp IF NOT EXISTS FOR (m:Moment) ON (m.timestamp);
