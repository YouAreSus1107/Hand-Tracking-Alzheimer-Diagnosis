# Wearable: Sensor Glove, OpenSim & Co-contraction

Maps to: the **Hand Digital Twin** device (see [`GLOVE_FIRMWARE_PLAN.md`](../docs/GLOVE_FIRMWARE_PLAN.md)).

## The core novelty check
The device's claim is that hand-muscle **co-contraction**, reconstructed from a
consumer glove via a biomechanical model, as an **early cognitive-decline**
marker, is an *unoccupied* intersection. The searches below support each
*component* being established while finding **no** existing hand-co-contraction
→ cognitive-decline system — consistent with the novelty claim (absence of
evidence, not proof of first).

## Biomechanical modeling / digital twins

**Sensor-driven digital twin for post-stroke gait (Cambridge, Wearable Tech.)**
[cambridge.org — wearable gait lab digital twin](https://www.cambridge.org/core/journals/wearable-technologies/article/wearable-gait-lab-powered-by-sensordriven-digital-twins-for-quantitative-biomechanical-analysis-poststroke/05C0872598A6602725105FA6EFE3C2EE)
A wearable-sensor-driven digital twin estimates internal biomechanics and flags
abnormal muscle activity (co-contraction/spasticity) post-stroke.
→ **The template.** Same architecture (wearable → model → internal forces),
proven for legs/stroke. The device applies it to the *hand* for *cognition* —
the transfer to justify.

**NeuroMotion — open-source EMG simulator with OpenSim (PLOS Comp Bio 2024)**
[PMC11251629](https://pmc.ncbi.nlm.nih.gov/articles/PMC11251629/)
Generates surface-EMG during voluntary hand/wrist movement; muscle-fiber lengths
from OpenSim.
→ Lets you *simulate/validate* the EMG↔activation link before/without perfect
hardware, de-risking the MyoWare EMG channel.

**OpenSim "When biomechanics meets reality" — the simulation gap (2025)**
[SmartDATA Lab](https://smartdata.ece.ufl.edu/index.php/2025/05/21/when-biomechanics-meets-reality-the-opensim-simulation-gap/)
Candid discussion of where OpenSim predictions diverge from measured reality.
→ Read before trusting the twin — sets realistic expectations on calibration
and model error (echoing the design notes' §7.3 risks).

## Glove hardware (FSR + flex + Arduino)

**Grip-strength system with FSR + flex sensors + SVM**
[ResearchGate](https://www.researchgate.net/publication/354287499_Design_of_grip_strength_measuring_system_using_FSR_and_flex_sensors_using_SVM_algorithm)
FSR + flex glove estimates grip force with an ML model.
→ Confirms the exact sensor pairing works for force estimation; a calibration
reference.

**Open glove repos:**
[SoloScriptSage/robotic-hand-project](https://github.com/SoloScriptSage/robotic-hand-project) ·
[ha3222/robot-hand-flex-sensor](https://github.com/ha3222/robot-hand-flex-sensor) ·
[GitHub `flex-sensor` topic](https://github.com/topics/flex-sensor)
→ Adaptable Arduino read + flex-to-angle mapping code for build Steps 2–8; port
the serial-to-bone-rotation logic to Python.

**Data-glove grasp-synergy / force-profiling studies**
[Instrumented glove grasp synergies (arXiv 2405.19430)](https://arxiv.org/pdf/2405.19430) ·
[Wearable sensors for grip-force profiling (arXiv 2011.05863)](https://arxiv.org/pdf/2011.05863)
→ Methods for turning multi-point glove force into meaningful synergy/force
features — relevant to deriving a co-contraction index.

## OpenSim hand model
The **ARMs Wrist and Hand Model** (OpenSim/SimTK) provides validated finger-muscle
attachments across MCP/PIP/DIP joints — the model to drive with calibrated
angles/forces (the design notes Step 10).

## Takeaways for this project
1. **Follow the post-stroke gait digital-twin architecture** — it's the proven
   blueprint; the hand+cognition application is the novel part.
2. **Validate the EMG/activation link with NeuroMotion** in simulation before
   relying on hardware EMG.
3. **Reuse open glove firmware** for Steps 2–8; spend the real effort on
   **calibration** (FSR→newtons, flex→degrees) and the **co-contraction index**.
4. Treat novelty as "not found in the literature," per the design notes — and make
   **validation on real cognitive-status groups** the headline contribution.
