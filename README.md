# Capstone Project: MedGraph AI

> [Wersja polska](#projekt-medgraph-ai)

---

## Running the Project (Docker)

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running

### 1. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in:

```
OPENAI_API_KEY=sk-...
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password_here
```

### 2. Add medication PDFs

Place PDF files (drug leaflets, SmPC documents) in `data/pdfs/`.

### 3. Set up the database

Start Neo4j, then apply the graph schema (constraints + indexes):

```bash
docker compose up neo4j -d
docker compose --profile setup run --rm setup
```

Neo4j Browser is available at `http://localhost:7474` once healthy.

### 4. Run ingestion (one-shot)

Loads all PDFs, extracts entities via GPT-4o, and builds the knowledge graph in Neo4j.

```bash
docker compose --profile ingest run --rm ingest
```

Re-run this whenever you add new PDFs. It is safe to re-run — duplicate data is not created.

### 5. Start the app

```bash
docker compose up app
```

Open `http://localhost:8501` in your browser.

### Stopping everything

```bash
docker compose down
```

To also delete the Neo4j graph data (full reset):

```bash
docker compose down -v
```

### Rebuilding after code changes

```bash
docker compose build
```

Or rebuild a specific service only:

```bash
docker compose build app
docker compose build ingest
```

---

## What You'll Build

A natural language interface for searching medication information from pharmaceutical PDF documents, powered by **GraphRAG** and a structured knowledge graph.

The system will process **PDF documents about medications**, including drug leaflets, prescribing information, SPCs(medication characteristics), formularies, and interaction references. It will convert this content into structured knowledge and answer complex questions such as:

- dosage guidance from official documents
- contraindications and warnings
- drug-drug interactions
- substitution or therapeutic alternatives
- medication suitability based on patient context

---

## Learning Goals
- Implement **GraphRAG** for medical/pharmaceutical documents
- Build a **knowledge graph** from unstructured PDF data
- Design a system that answers **complex medication questions with citations**
- Add **safety guardrails** for high-stakes domains

---

## Project Overview

### Problem
Healthcare professionals and patients often struggle because medication information is:
- spread across many PDF documents
- difficult to search quickly
- full of cross-references between warnings, interactions, age groups, and dosage rules
- risky to interpret without proper source grounding

Traditional document search may retrieve relevant paragraphs, but it often fails when the question requires connecting multiple facts, for example:
- age + body mass + contraindications
- drug A + drug B + kidney impairment
- substitute medication + same active substance/class + restrictions

### Solution
Build a **GraphRAG-based medication assistant** that:
- ingests medication PDFs
- extracts entities such as:
    - drug name
    - active ingredient
    - dosage form
    - indication
    - contraindication
    - adverse effect
    - interaction
    - age restriction
    - weight-based dosing rule
    - pregnancy/lactation warning
    - substitution/alternative relationships
- stores them in a **knowledge graph**
- answers user questions with:
    - grounded retrieval
    - reasoning across connected medical facts
    - references to original document sections

---

## Key Queries to Support
Your system should answer questions like
- “What is the recommended dose of Drug X for a child weighing 25 kg?”
- “Can Drug A be mixed with Drug B?”
- “Which medications are contraindicated in pregnancy?”
- “What alternatives exist for Drug X with the same active ingredient?”
- “Which medications should be avoided for elderly patients?”
- “What warnings apply if the patient has liver or kidney impairment?”
- “Which drugs interact with ibuprofen?”
- “What is the difference between Drug A and Drug B?”

Important project rule:
- For dosage, substitutions, and interaction questions, the system must return **source-cited answers** and clearly state that final decisions require **doctor/pharmacist verification**.

---

## Deliverables
- Natural language medication query interface 
- PDF ingestion pipeline for medication documents
- Knowledge graph extracted from pharmaceutical texts
- GraphRAG query engine
- Evaluation report demonstrating system accuracy and citation quality
- Demo application with citations and safety notices

---

## Success Criteria

### Minimum Requirements

- Extract knowledge graph from **30+ medication PDFs**
- Identify and store key medical/pharmaceutical entities and relationships
- Answer at least **10 medication intelligence queries correctly**
- Answer multi-hop clinical queries using **GraphRAG** reasoning
- Provide document-grounded answers with citations
- Complete technical documentation and demo

### Advanced Features (Bonus)
- Drug interaction graph visualization
- Patient profile input:
    - age
    - weight
    - pregnancy status
    - kidney/liver impairment
- Explainable answers with highlighted evidence
- Multilingual PDF support
- Confidence scoring and safety-risk classification
- Dashboard for exploring medication relationships
- Detection of conflicting information across sources

---

## Core Use Cases to Solve

System should handle these realistic scenarios:

### Dosage Guidance

“What dose of Drug X is described for a patient aged 8 years and weighing 30 kg?”

### Interaction Check

“Can Drug A and Drug B be taken together?”

### Contraindication Search

“Which medications should be avoided during pregnancy?”

### Substitution Support

“What can be used as an alternative to Drug X?”

### Safety Screening

“What warnings apply to this medication for elderly patients?”

### Multi-Hop Clinical Query

“Which pain medications are suitable for a patient with gastric ulcer risk and which should be avoided?”

---

## Getting Started

### Suggested Data Sources

Start with structured and semi-structured medication PDFs such as:

- package inserts / PILs
- SmPC / SPC documents
- drug formularies
- hospital guidelines
- interaction reference sheets


---

## Safety & Compliance Requirements

Because this is a medical domain, your system should include:

- **citation-first answers**
- clear statement that it is a **decision-support tool**, not a replacement for a clinician
- refusal or caution on unsupported/high-risk questions
- warning when evidence is missing or ambiguous
- distinction between:
    - exact source-backed information    
    - inferred or approximate reasoning
- logs for traceability of answer generation

Good rule:

> The system should never invent a dose, interaction, or substitute.  
> It should only answer from retrieved evidence or explicitly say the information was not found.

---

## Extension Areas

You can extend the system with:

- patient-profile-aware query interpretation
- ATC classification integration
- drug class reasoning
- interaction severity ranking
- explainable recommendation engine
- evidence highlighting inside PDF sections
- multilingual medication document support
- dashboard for clinicians or pharmacists

---

## Final Goal

Build a professional **AI medication knowledge system** that solves a real-world healthcare information problem while demonstrating advanced **GraphRAG techniques**, retrieval quality, and safe AI design.

This can become a very strong portfolio project because it shows:
- LLM application in a high-stakes domain
- graph-based reasoning
- document intelligence
- evaluation discipline
- practical system design with safety considerations

---

---

# Projekt MedGraph AI

> [English version](#capstone-project-medgraph-ai)

## Co budujesz

Interfejs języka naturalnego do wyszukiwania informacji o lekach z farmaceutycznych dokumentów PDF, oparty na **GraphRAG** i ustrukturyzowanym grafie wiedzy.

System przetwarza **dokumenty PDF o lekach**, w tym ulotki dla pacjenta, charakterystyki produktu (SmPC), formularze i zestawienia interakcji. Konwertuje je na ustrukturyzowaną wiedzę i odpowiada na złożone pytania takie jak:

- dawkowanie na podstawie oficjalnych dokumentów
- przeciwwskazania i ostrzeżenia
- interakcje lek-lek
- zamienniki i alternatywy terapeutyczne
- bezpieczeństwo stosowania leku w kontekście pacjenta

---

## Cele edukacyjne

- Wdrożenie **GraphRAG** dla dokumentów medycznych i farmaceutycznych
- Budowa **grafu wiedzy** z nieustrukturyzowanych danych PDF
- Zaprojektowanie systemu odpowiadającego na **złożone pytania o lekach z cytowaniami**
- Dodanie **zabezpieczeń** dla dziedzin wysokiego ryzyka

---

## Przegląd projektu

### Problem

Pracownicy służby zdrowia i pacjenci mają trudności, ponieważ informacje o lekach są:
- rozproszone w wielu dokumentach PDF
- trudne do szybkiego przeszukania
- pełne wzajemnych odniesień między ostrzeżeniami, interakcjami, grupami wiekowymi i zasadami dawkowania
- ryzykowne w interpretacji bez właściwego ugruntowania w źródle

Tradycyjne wyszukiwanie dokumentów może zwracać trafne fragmenty, ale zawodzi gdy pytanie wymaga połączenia wielu faktów, np.:
- wiek + masa ciała + przeciwwskazania
- lek A + lek B + niewydolność nerek
- zamiennik + ta sama substancja czynna + ograniczenia

### Rozwiązanie

Zbuduj **asystenta lekowego opartego na GraphRAG**, który:
- wczytuje dokumenty PDF o lekach
- ekstrahuje encje takie jak:
    - nazwa leku
    - substancja czynna
    - postać farmaceutyczna
    - wskazanie
    - przeciwwskazanie
    - działanie niepożądane
    - interakcja
    - ograniczenie wiekowe
    - reguła dawkowania zależna od masy ciała
    - ostrzeżenie dotyczące ciąży/laktacji
    - relacje zamienników i alternatyw
- przechowuje je w **grafie wiedzy**
- odpowiada na pytania z:
    - ugruntowanym wyszukiwaniem
    - rozumowaniem po połączonych faktach medycznych
    - odniesieniami do oryginalnych sekcji dokumentów

---

## Obsługiwane zapytania

System powinien odpowiadać na pytania takie jak:
- "Jaka jest zalecana dawka leku X dla dziecka ważącego 25 kg?"
- "Czy lek A można łączyć z lekiem B?"
- "Które leki są przeciwwskazane w ciąży?"
- "Jakie alternatywy istnieją dla leku X z tym samym składnikiem aktywnym?"
- "Których leków należy unikać u pacjentów w podeszłym wieku?"
- "Jakie ostrzeżenia dotyczą pacjenta z niewydolnością wątroby lub nerek?"
- "Które leki wchodzą w interakcję z ibuprofenem?"

Ważna zasada projektu:
- W przypadku pytań o dawkowanie, zamienniki i interakcje system musi zwracać **odpowiedzi z cytowaniem źródła** i wyraźnie stwierdzać, że ostateczne decyzje wymagają **weryfikacji przez lekarza lub farmaceutę**.

---

## Produkty końcowe

- Interfejs zapytań o leki w języku naturalnym
- Pipeline do wczytywania dokumentów PDF o lekach
- Graf wiedzy wyekstrahowany z tekstów farmaceutycznych
- Silnik zapytań GraphRAG
- Raport ewaluacyjny pokazujący dokładność systemu i jakość cytowań
- Aplikacja demonstracyjna z cytowaniami i informacjami bezpieczeństwa

---

## Kryteria sukcesu

### Wymagania minimalne

- Wyekstrahowanie grafu wiedzy z **30+ dokumentów PDF o lekach**
- Identyfikacja i przechowywanie kluczowych encji i relacji medycznych
- Poprawna odpowiedź na co najmniej **10 zapytań**
- Obsługa wieloetapowych zapytań klinicznych z użyciem rozumowania **GraphRAG**
- Odpowiedzi ugruntowane w dokumentach z cytowaniami
- Kompletna dokumentacja techniczna i demo

### Funkcje zaawansowane (opcjonalne)

- Wizualizacja grafu interakcji lekowych
- Wprowadzanie profilu pacjenta:
    - wiek
    - waga
    - status ciąży
    - niewydolność nerek/wątroby
- Wyjaśnialne odpowiedzi z wyróżnionymi dowodami
- Obsługa wielojęzycznych dokumentów PDF
- Ocena pewności i klasyfikacja ryzyka bezpieczeństwa
- Dashboard do eksplorowania relacji między lekami
- Wykrywanie sprzecznych informacji między źródłami

---

## Podstawowe przypadki użycia

### Wskazówki dotyczące dawkowania

"Jaka dawka leku X jest opisana dla pacjenta w wieku 8 lat i wadze 30 kg?"

### Sprawdzenie interakcji

"Czy lek A i lek B można stosować jednocześnie?"

### Wyszukiwanie przeciwwskazań

"Których leków należy unikać w ciąży?"

### Wsparcie przy zamianie leku

"Czym można zastąpić lek X?"

### Screening bezpieczeństwa

"Jakie ostrzeżenia dotyczą tego leku u pacjentów w podeszłym wieku?"

### Wieloetapowe zapytanie kliniczne

"Które leki przeciwbólowe są odpowiednie dla pacjenta z ryzykiem choroby wrzodowej żołądka i których należy unikać?"

---

## Rozpoczęcie pracy

### Sugerowane źródła danych

Zacznij od ustrukturyzowanych i częściowo ustrukturyzowanych dokumentów PDF o lekach, takich jak:

- ulotki dla pacjenta (PIL)
- dokumenty SmPC / SPC
- formularze lekowe
- wytyczne szpitalne
- zestawienia interakcji

---

## Wymagania bezpieczeństwa i zgodności

Ponieważ jest to dziedzina medyczna, system powinien zawierać:

- **odpowiedzi oparte na cytowaniach**
- wyraźne stwierdzenie, że jest to **narzędzie wspomagające decyzje**, a nie zastępstwo dla klinicysty
- odmowę lub ostrożność przy pytaniach nieobsługiwanych lub wysokiego ryzyka
- ostrzeżenie gdy dowody są brakujące lub niejednoznaczne
- rozróżnienie między:
    - informacjami dokładnie potwierdzonymi źródłem
    - rozumowaniem przybliżonym lub wnioskowanym
- logi dla identyfikowalności generowania odpowiedzi
- sugestię konsultacji z lekarzem przed rozpoczęciem terapii

Dobra zasada:

> System nigdy nie powinien wymyślać dawki, interakcji ani zamiennika.
> Powinien odpowiadać wyłącznie na podstawie pobranych dowodów lub wprost stwierdzać, że informacji nie znaleziono.

---

## Obszary rozszerzeń

System można rozszerzyć o:

- interpretację zapytań z uwzględnieniem profilu pacjenta
- integrację klasyfikacji ATC
- rozumowanie oparte na klasach leków
- ranking ciężkości interakcji
- wyjaśnialny silnik rekomendacji
- wyróżnianie dowodów wewnątrz sekcji PDF
- obsługę wielojęzycznych dokumentów o lekach
- dashboard dla klinicystów lub farmaceutów

---

## Cel końcowy

Zbuduj profesjonalny **system wiedzy o lekach oparty na AI**, który rozwiązuje rzeczywisty problem z dziedziny informacji medycznej, demonstrując zaawansowane **techniki GraphRAG**, jakość wyszukiwania i bezpieczny projekt AI.

Może to stać się bardzo mocnym projektem portfolio, ponieważ pokazuje:
- zastosowanie LLM w dziedzinie wysokiego ryzyka
- rozumowanie oparte na grafie
- inteligencję dokumentową
- dyscyplinę ewaluacji
- praktyczny projekt systemu z uwzględnieniem bezpieczeństwa
