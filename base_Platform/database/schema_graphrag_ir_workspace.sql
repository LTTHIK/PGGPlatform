-- GraphRAG / IR / Wiki 工作区扩展表（9 张）
-- 在 ltt_craft 库、基础表（users / file_records 等）就绪后执行。
-- 幂等：若表已存在，请仅作结构参考；全新库可配合 psql ON_ERROR_STOP 执行。
--
-- 依赖：
--   CREATE EXTENSION IF NOT EXISTS pgcrypto;
--   set_updated_at() 触发器函数（见 schema_all_tables.sql 或下方）

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE OR REPLACE FUNCTION public.set_updated_at()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$function$;

--
-- PostgreSQL database dump
--


-- Dumped from database version 16.13
-- Dumped by pg_dump version 16.13

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: analysis_task_events; Type: TABLE; Schema: public; Owner: craft
--

CREATE TABLE public.analysis_task_events (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    task_id uuid NOT NULL,
    event_type text NOT NULL,
    message text,
    payload_json jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.analysis_task_events OWNER TO craft;

--
-- Name: analysis_task_files; Type: TABLE; Schema: public; Owner: craft
--

CREATE TABLE public.analysis_task_files (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    task_id uuid NOT NULL,
    project_id uuid NOT NULL,
    file_record_id bigint,
    filename text NOT NULL,
    file_ext text,
    content_type text,
    byte_length bigint,
    minio_bucket text,
    minio_object_key text,
    local_path text,
    raw_workspace_path text,
    parsed_text_path text,
    graphrag_input_path text,
    parse_status text DEFAULT 'pending'::text NOT NULL,
    parse_error text,
    source_role text DEFAULT 'analysis_input'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.analysis_task_files OWNER TO craft;

--
-- Name: analysis_tasks; Type: TABLE; Schema: public; Owner: craft
--

CREATE TABLE public.analysis_tasks (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    project_id uuid NOT NULL,
    project_code text NOT NULL,
    skill_id text NOT NULL,
    mode text NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    progress integer DEFAULT 0 NOT NULL,
    current_step text,
    error_message text,
    model_task_id text,
    model_status text,
    workspace_task_path text,
    created_by bigint,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    finished_at timestamp with time zone
);


ALTER TABLE public.analysis_tasks OWNER TO craft;

--
-- Name: candidate_ir_items; Type: TABLE; Schema: public; Owner: craft
--

CREATE TABLE public.candidate_ir_items (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    task_id uuid NOT NULL,
    project_id uuid NOT NULL,
    title text NOT NULL,
    ir_type text,
    category text,
    content_json jsonb NOT NULL,
    source_refs_json jsonb,
    crr_refs_json jsonb,
    confidence numeric,
    rationale text,
    status text DEFAULT 'draft'::text NOT NULL,
    created_by bigint,
    created_by_model text,
    model_version text,
    reviewed_by bigint,
    reviewed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.candidate_ir_items OWNER TO craft;

--
-- Name: crr_snapshots; Type: TABLE; Schema: public; Owner: craft
--

CREATE TABLE public.crr_snapshots (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    task_id uuid NOT NULL,
    project_id uuid NOT NULL,
    crr_code text,
    canonical_title text NOT NULL,
    canonical_type text NOT NULL,
    summary text,
    content_json jsonb NOT NULL,
    artifact_refs_json jsonb,
    source_refs_json jsonb,
    entities_json jsonb,
    relationships_json jsonb,
    confidence numeric,
    status text DEFAULT 'candidate'::text NOT NULL,
    wiki_path text,
    created_by_model text,
    model_artifact_id uuid,
    reviewed_by bigint,
    reviewed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.crr_snapshots OWNER TO craft;

--
-- Name: ir_assets; Type: TABLE; Schema: public; Owner: craft
--

CREATE TABLE public.ir_assets (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    project_id uuid NOT NULL,
    ir_code text NOT NULL,
    title text NOT NULL,
    ir_type text,
    category text,
    content_json jsonb NOT NULL,
    source_refs_json jsonb,
    crr_refs_json jsonb,
    wiki_path text,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_by bigint,
    promoted_from_candidate_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.ir_assets OWNER TO craft;

--
-- Name: model_artifacts; Type: TABLE; Schema: public; Owner: craft
--

CREATE TABLE public.model_artifacts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    task_id uuid NOT NULL,
    project_id uuid NOT NULL,
    model_task_id text,
    model_version text,
    adapter_type text,
    manifest_path text,
    manifest_json jsonb,
    project_root text,
    input_dir text,
    output_dir text,
    lancedb_uri text,
    entities_path text,
    relationships_path text,
    text_units_path text,
    communities_path text,
    community_reports_path text,
    entity_count integer,
    relationship_count integer,
    text_unit_count integer,
    community_count integer,
    community_report_count integer,
    stdout_path text,
    stderr_path text,
    status text DEFAULT 'pending'::text NOT NULL,
    error_message text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.model_artifacts OWNER TO craft;

--
-- Name: projects; Type: TABLE; Schema: public; Owner: craft
--

CREATE TABLE public.projects (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    project_code text NOT NULL,
    project_name text NOT NULL,
    project_slug text NOT NULL,
    workspace_root text,
    description text,
    created_by bigint,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.projects OWNER TO craft;

--
-- Name: wiki_pages; Type: TABLE; Schema: public; Owner: craft
--

CREATE TABLE public.wiki_pages (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    project_id uuid NOT NULL,
    page_type text NOT NULL,
    slug text NOT NULL,
    title text NOT NULL,
    wiki_path text NOT NULL,
    source_object_type text,
    source_object_id text,
    frontmatter_json jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.wiki_pages OWNER TO craft;

--
-- Name: analysis_task_events analysis_task_events_pkey; Type: CONSTRAINT; Schema: public; Owner: craft
--

ALTER TABLE ONLY public.analysis_task_events
    ADD CONSTRAINT analysis_task_events_pkey PRIMARY KEY (id);


--
-- Name: analysis_task_files analysis_task_files_pkey; Type: CONSTRAINT; Schema: public; Owner: craft
--

ALTER TABLE ONLY public.analysis_task_files
    ADD CONSTRAINT analysis_task_files_pkey PRIMARY KEY (id);


--
-- Name: analysis_tasks analysis_tasks_pkey; Type: CONSTRAINT; Schema: public; Owner: craft
--

ALTER TABLE ONLY public.analysis_tasks
    ADD CONSTRAINT analysis_tasks_pkey PRIMARY KEY (id);


--
-- Name: candidate_ir_items candidate_ir_items_pkey; Type: CONSTRAINT; Schema: public; Owner: craft
--

ALTER TABLE ONLY public.candidate_ir_items
    ADD CONSTRAINT candidate_ir_items_pkey PRIMARY KEY (id);


--
-- Name: crr_snapshots crr_snapshots_pkey; Type: CONSTRAINT; Schema: public; Owner: craft
--

ALTER TABLE ONLY public.crr_snapshots
    ADD CONSTRAINT crr_snapshots_pkey PRIMARY KEY (id);


--
-- Name: ir_assets ir_assets_ir_code_key; Type: CONSTRAINT; Schema: public; Owner: craft
--

ALTER TABLE ONLY public.ir_assets
    ADD CONSTRAINT ir_assets_ir_code_key UNIQUE (ir_code);


--
-- Name: ir_assets ir_assets_pkey; Type: CONSTRAINT; Schema: public; Owner: craft
--

ALTER TABLE ONLY public.ir_assets
    ADD CONSTRAINT ir_assets_pkey PRIMARY KEY (id);


--
-- Name: model_artifacts model_artifacts_pkey; Type: CONSTRAINT; Schema: public; Owner: craft
--

ALTER TABLE ONLY public.model_artifacts
    ADD CONSTRAINT model_artifacts_pkey PRIMARY KEY (id);


--
-- Name: projects projects_pkey; Type: CONSTRAINT; Schema: public; Owner: craft
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_pkey PRIMARY KEY (id);


--
-- Name: projects projects_project_code_key; Type: CONSTRAINT; Schema: public; Owner: craft
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_project_code_key UNIQUE (project_code);


--
-- Name: projects projects_project_slug_key; Type: CONSTRAINT; Schema: public; Owner: craft
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_project_slug_key UNIQUE (project_slug);


--
-- Name: wiki_pages wiki_pages_pkey; Type: CONSTRAINT; Schema: public; Owner: craft
--

ALTER TABLE ONLY public.wiki_pages
    ADD CONSTRAINT wiki_pages_pkey PRIMARY KEY (id);


--
-- Name: wiki_pages wiki_pages_project_id_wiki_path_key; Type: CONSTRAINT; Schema: public; Owner: craft
--

ALTER TABLE ONLY public.wiki_pages
    ADD CONSTRAINT wiki_pages_project_id_wiki_path_key UNIQUE (project_id, wiki_path);


--
-- Name: idx_analysis_task_events_task; Type: INDEX; Schema: public; Owner: craft
--

CREATE INDEX idx_analysis_task_events_task ON public.analysis_task_events USING btree (task_id, created_at DESC);


--
-- Name: idx_analysis_task_events_type; Type: INDEX; Schema: public; Owner: craft
--

CREATE INDEX idx_analysis_task_events_type ON public.analysis_task_events USING btree (event_type, created_at DESC);


--
-- Name: idx_analysis_task_files_file_record; Type: INDEX; Schema: public; Owner: craft
--

CREATE INDEX idx_analysis_task_files_file_record ON public.analysis_task_files USING btree (file_record_id);


--
-- Name: idx_analysis_task_files_parse_status; Type: INDEX; Schema: public; Owner: craft
--

CREATE INDEX idx_analysis_task_files_parse_status ON public.analysis_task_files USING btree (parse_status);


--
-- Name: idx_analysis_task_files_task; Type: INDEX; Schema: public; Owner: craft
--

CREATE INDEX idx_analysis_task_files_task ON public.analysis_task_files USING btree (task_id);


--
-- Name: idx_analysis_tasks_model_task; Type: INDEX; Schema: public; Owner: craft
--

CREATE INDEX idx_analysis_tasks_model_task ON public.analysis_tasks USING btree (model_task_id);


--
-- Name: idx_analysis_tasks_project; Type: INDEX; Schema: public; Owner: craft
--

CREATE INDEX idx_analysis_tasks_project ON public.analysis_tasks USING btree (project_id, created_at DESC);


--
-- Name: idx_analysis_tasks_status; Type: INDEX; Schema: public; Owner: craft
--

CREATE INDEX idx_analysis_tasks_status ON public.analysis_tasks USING btree (status, created_at DESC);


--
-- Name: idx_candidate_ir_project; Type: INDEX; Schema: public; Owner: craft
--

CREATE INDEX idx_candidate_ir_project ON public.candidate_ir_items USING btree (project_id, created_at DESC);


--
-- Name: idx_candidate_ir_status; Type: INDEX; Schema: public; Owner: craft
--

CREATE INDEX idx_candidate_ir_status ON public.candidate_ir_items USING btree (status);


--
-- Name: idx_candidate_ir_task; Type: INDEX; Schema: public; Owner: craft
--

CREATE INDEX idx_candidate_ir_task ON public.candidate_ir_items USING btree (task_id);


--
-- Name: idx_crr_snapshots_project; Type: INDEX; Schema: public; Owner: craft
--

CREATE INDEX idx_crr_snapshots_project ON public.crr_snapshots USING btree (project_id, created_at DESC);


--
-- Name: idx_crr_snapshots_status; Type: INDEX; Schema: public; Owner: craft
--

CREATE INDEX idx_crr_snapshots_status ON public.crr_snapshots USING btree (status);


--
-- Name: idx_crr_snapshots_task; Type: INDEX; Schema: public; Owner: craft
--

CREATE INDEX idx_crr_snapshots_task ON public.crr_snapshots USING btree (task_id);


--
-- Name: idx_crr_snapshots_type; Type: INDEX; Schema: public; Owner: craft
--

CREATE INDEX idx_crr_snapshots_type ON public.crr_snapshots USING btree (canonical_type);


--
-- Name: idx_ir_assets_candidate; Type: INDEX; Schema: public; Owner: craft
--

CREATE INDEX idx_ir_assets_candidate ON public.ir_assets USING btree (promoted_from_candidate_id);


--
-- Name: idx_ir_assets_project; Type: INDEX; Schema: public; Owner: craft
--

CREATE INDEX idx_ir_assets_project ON public.ir_assets USING btree (project_id, created_at DESC);


--
-- Name: idx_ir_assets_status; Type: INDEX; Schema: public; Owner: craft
--

CREATE INDEX idx_ir_assets_status ON public.ir_assets USING btree (status);


--
-- Name: idx_model_artifacts_model_task; Type: INDEX; Schema: public; Owner: craft
--

CREATE INDEX idx_model_artifacts_model_task ON public.model_artifacts USING btree (model_task_id);


--
-- Name: idx_model_artifacts_project; Type: INDEX; Schema: public; Owner: craft
--

CREATE INDEX idx_model_artifacts_project ON public.model_artifacts USING btree (project_id, created_at DESC);


--
-- Name: idx_model_artifacts_task; Type: INDEX; Schema: public; Owner: craft
--

CREATE INDEX idx_model_artifacts_task ON public.model_artifacts USING btree (task_id);


--
-- Name: idx_projects_slug; Type: INDEX; Schema: public; Owner: craft
--

CREATE INDEX idx_projects_slug ON public.projects USING btree (project_slug);


--
-- Name: idx_wiki_pages_project; Type: INDEX; Schema: public; Owner: craft
--

CREATE INDEX idx_wiki_pages_project ON public.wiki_pages USING btree (project_id, page_type);


--
-- Name: idx_wiki_pages_source; Type: INDEX; Schema: public; Owner: craft
--

CREATE INDEX idx_wiki_pages_source ON public.wiki_pages USING btree (source_object_type, source_object_id);


--
-- Name: analysis_task_files trg_analysis_task_files_updated; Type: TRIGGER; Schema: public; Owner: craft
--

CREATE TRIGGER trg_analysis_task_files_updated BEFORE UPDATE ON public.analysis_task_files FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: analysis_tasks trg_analysis_tasks_updated; Type: TRIGGER; Schema: public; Owner: craft
--

CREATE TRIGGER trg_analysis_tasks_updated BEFORE UPDATE ON public.analysis_tasks FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: candidate_ir_items trg_candidate_ir_items_updated; Type: TRIGGER; Schema: public; Owner: craft
--

CREATE TRIGGER trg_candidate_ir_items_updated BEFORE UPDATE ON public.candidate_ir_items FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: crr_snapshots trg_crr_snapshots_updated; Type: TRIGGER; Schema: public; Owner: craft
--

CREATE TRIGGER trg_crr_snapshots_updated BEFORE UPDATE ON public.crr_snapshots FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: ir_assets trg_ir_assets_updated; Type: TRIGGER; Schema: public; Owner: craft
--

CREATE TRIGGER trg_ir_assets_updated BEFORE UPDATE ON public.ir_assets FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: model_artifacts trg_model_artifacts_updated; Type: TRIGGER; Schema: public; Owner: craft
--

CREATE TRIGGER trg_model_artifacts_updated BEFORE UPDATE ON public.model_artifacts FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: projects trg_projects_updated; Type: TRIGGER; Schema: public; Owner: craft
--

CREATE TRIGGER trg_projects_updated BEFORE UPDATE ON public.projects FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: wiki_pages trg_wiki_pages_updated; Type: TRIGGER; Schema: public; Owner: craft
--

CREATE TRIGGER trg_wiki_pages_updated BEFORE UPDATE ON public.wiki_pages FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: analysis_task_events analysis_task_events_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: craft
--

ALTER TABLE ONLY public.analysis_task_events
    ADD CONSTRAINT analysis_task_events_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.analysis_tasks(id) ON DELETE CASCADE;


--
-- Name: analysis_task_files analysis_task_files_file_record_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: craft
--

ALTER TABLE ONLY public.analysis_task_files
    ADD CONSTRAINT analysis_task_files_file_record_id_fkey FOREIGN KEY (file_record_id) REFERENCES public.file_records(id);


--
-- Name: analysis_task_files analysis_task_files_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: craft
--

ALTER TABLE ONLY public.analysis_task_files
    ADD CONSTRAINT analysis_task_files_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: analysis_task_files analysis_task_files_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: craft
--

ALTER TABLE ONLY public.analysis_task_files
    ADD CONSTRAINT analysis_task_files_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.analysis_tasks(id) ON DELETE CASCADE;


--
-- Name: analysis_tasks analysis_tasks_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: craft
--

ALTER TABLE ONLY public.analysis_tasks
    ADD CONSTRAINT analysis_tasks_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: analysis_tasks analysis_tasks_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: craft
--

ALTER TABLE ONLY public.analysis_tasks
    ADD CONSTRAINT analysis_tasks_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: candidate_ir_items candidate_ir_items_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: craft
--

ALTER TABLE ONLY public.candidate_ir_items
    ADD CONSTRAINT candidate_ir_items_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: candidate_ir_items candidate_ir_items_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: craft
--

ALTER TABLE ONLY public.candidate_ir_items
    ADD CONSTRAINT candidate_ir_items_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: candidate_ir_items candidate_ir_items_reviewed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: craft
--

ALTER TABLE ONLY public.candidate_ir_items
    ADD CONSTRAINT candidate_ir_items_reviewed_by_fkey FOREIGN KEY (reviewed_by) REFERENCES public.users(id);


--
-- Name: candidate_ir_items candidate_ir_items_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: craft
--

ALTER TABLE ONLY public.candidate_ir_items
    ADD CONSTRAINT candidate_ir_items_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.analysis_tasks(id) ON DELETE CASCADE;


--
-- Name: crr_snapshots crr_snapshots_model_artifact_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: craft
--

ALTER TABLE ONLY public.crr_snapshots
    ADD CONSTRAINT crr_snapshots_model_artifact_id_fkey FOREIGN KEY (model_artifact_id) REFERENCES public.model_artifacts(id);


--
-- Name: crr_snapshots crr_snapshots_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: craft
--

ALTER TABLE ONLY public.crr_snapshots
    ADD CONSTRAINT crr_snapshots_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: crr_snapshots crr_snapshots_reviewed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: craft
--

ALTER TABLE ONLY public.crr_snapshots
    ADD CONSTRAINT crr_snapshots_reviewed_by_fkey FOREIGN KEY (reviewed_by) REFERENCES public.users(id);


--
-- Name: crr_snapshots crr_snapshots_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: craft
--

ALTER TABLE ONLY public.crr_snapshots
    ADD CONSTRAINT crr_snapshots_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.analysis_tasks(id) ON DELETE CASCADE;


--
-- Name: ir_assets ir_assets_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: craft
--

ALTER TABLE ONLY public.ir_assets
    ADD CONSTRAINT ir_assets_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: ir_assets ir_assets_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: craft
--

ALTER TABLE ONLY public.ir_assets
    ADD CONSTRAINT ir_assets_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: ir_assets ir_assets_promoted_from_candidate_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: craft
--

ALTER TABLE ONLY public.ir_assets
    ADD CONSTRAINT ir_assets_promoted_from_candidate_id_fkey FOREIGN KEY (promoted_from_candidate_id) REFERENCES public.candidate_ir_items(id);


--
-- Name: model_artifacts model_artifacts_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: craft
--

ALTER TABLE ONLY public.model_artifacts
    ADD CONSTRAINT model_artifacts_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: model_artifacts model_artifacts_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: craft
--

ALTER TABLE ONLY public.model_artifacts
    ADD CONSTRAINT model_artifacts_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.analysis_tasks(id) ON DELETE CASCADE;


--
-- Name: projects projects_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: craft
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: wiki_pages wiki_pages_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: craft
--

ALTER TABLE ONLY public.wiki_pages
    ADD CONSTRAINT wiki_pages_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--


