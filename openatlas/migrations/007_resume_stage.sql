ALTER TABLE jobs ADD COLUMN stopped_stage TEXT;
UPDATE jobs SET stopped_stage = CASE
    WHEN stage IN ('planning','building','validating','publishing') THEN stage
    ELSE (SELECT stage FROM job_events WHERE job_id=jobs.id AND stage IN ('planning','building','validating','publishing') ORDER BY id DESC LIMIT 1)
END WHERE status='failed';
