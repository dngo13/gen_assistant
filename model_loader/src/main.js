import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm';
import { loadBVHAnimation, loadMixamoAnimation } from './animationLoader.js';

// renderer
const renderer = new THREE.WebGLRenderer();
renderer.setSize( window.innerWidth, window.innerHeight );
renderer.setPixelRatio( window.devicePixelRatio );
renderer.outputEncoding = THREE.sRGBEncoding;
document.body.appendChild( renderer.domElement );

// camera
const camera = new THREE.PerspectiveCamera( 15.0, window.innerWidth / window.innerHeight, 0.1, 20.0 );
camera.position.set( 0.0, 1.3, 3.56 );

// camera controls
const controls = new OrbitControls( camera, renderer.domElement );
controls.screenSpacePanning = true;
controls.target.set( 0.0, 1.33, -0.03 );
controls.update();

// scene
const scene = new THREE.Scene();

// light
const light = new THREE.DirectionalLight(0xffffff, 3.14);
light.position.set(1.0, 1.0, 1.0).normalize();
scene.add( light );

// gltf and vrm
let currentVrm = undefined;
let mixer; // animation mixer
const loader = new GLTFLoader();
loader.crossOrigin = 'anonymous';

//RGB sliders for solid color bg
const colorSliders = {
  r: document.createElement('input'),
  g: document.createElement('input'),
  b: document.createElement('input')
};

['r','g','b'].forEach((c, i) => {
  // Label
  const label = document.createElement('label');
  label.textContent = c.toUpperCase();
  label.style.position = 'absolute';
  label.style.left = '5px';
  label.style.top = `${70 + i*30}px`;
  label.style.color = 'white';
  label.style.fontFamily = 'monospace';
  document.body.appendChild(label);
  // Sliders
  const slider = colorSliders[c];
  slider.type = 'range';
  slider.min = 0;
  slider.max = 255;
  slider.value = 68; // initial gray
  slider.style.position = 'absolute';
  slider.style.left = '10px';
  slider.style.top = `${70 + i*30}px`;
  document.body.appendChild(slider);

  slider.addEventListener('input', () => {
    if (bgSelect.value === 'None') setBackground('None');
  });
});

// Background setup
const textureLoader = new THREE.TextureLoader();
const backgrounds = {
  'None': null,
  'CyberpunkBedroom': '/backgrounds/bedroom_cyberpunk.jpg',
  'Bedroom': '/backgrounds/bedroom.png',
  'GothicBedroom': '/backgrounds/gothic_bedroom.png',
  'NightBeach': '/backgrounds/landscape_beach_night.jpg',
  'StarryNight': '/backgrounds/Starry_Night.png'
};

function setBackground(name) {
  if (name === 'None') {
    // Use a solid color — read sliders for R/G/B
    const r = parseInt(colorSliders.r.value) / 255;
    const g = parseInt(colorSliders.g.value) / 255;
    const b = parseInt(colorSliders.b.value) / 255;
    scene.background = new THREE.Color(r, g, b);
    scene.environment = null;
    return;
  }
  const path = backgrounds[name];
  if (!path) {
    return;
  }
  textureLoader.load(path, (texture) => {
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.minFilter = THREE.LinearFilter;
    texture.magFilter = THREE.LinearFilter;

    scene.background = texture;
    scene.environment = null;
  });
}

loader.register( ( parser ) => {
  return new VRMLoaderPlugin( parser );
} );


// WebSocket and Audio setup
let audioContext = null;
let ws = null;
let isAnimatingMouth = false; // Flag to prevent animations from overlapping

// const ws = new WebSocket("ws://192.168.1.175:8765"); // connect to your Python TTS stream
// ws.binaryType = "arraybuffer";
// ws.onopen = () => {console.log("Websocket connected!")};
/////// this worked to animate mouth but didnt consider audio
// ws.onmessage = (msg) => {
//     try {
//         const data = JSON.parse(msg.data);
//         console.log("[WS] Received:", data);
//         if (data.event === "speak") {
//             const text = data.text || "";
//             const duration = data.duration || 0;
//             console.log(`[VRM] Speaking: "${text}" for ${duration.toFixed(2)}s`);

//             // Mock simple mouth animation timing
//             startMouthAnimation(duration);
//         }
//     } catch (err) {
//         console.error("[WS] Invalid message:", err, msg.data);
//     }
// };
//ws.onclose = () => console.log("Websocket - Closed connection");
// This function will be called when we have a decoded audio buffer
function animateMouthFromBuffer(buffer) {
    if (!currentVrm || isAnimatingMouth) {
        console.log("VRM not ready or mouth is already animating.");
        return;
    }
    isAnimatingMouth = true;

    const channelData = buffer.getChannelData(0); // Use the first channel
    const duration = buffer.duration;
    const sampleRate = buffer.sampleRate;
    let startTime = performance.now();

    function frame() {
        const elapsedTime = (performance.now() - startTime) / 1000; // in seconds

        if (elapsedTime >= duration) {
            setMouthOpen(0); // Close mouth at the end
            isAnimatingMouth = false;
            console.log("[VRM] Done speaking.");
            return; // Stop the animation
        }

        // Determine the current position in the audio data
        const currentIndex = Math.floor(elapsedTime * sampleRate);
        const sampleChunkSize = 1024; // Analyze chunks of 1024 samples
        let sum = 0;
        for (let i = 0; i < sampleChunkSize; i++) {
            sum += Math.abs(channelData[currentIndex + i] || 0);
        }
        const average = sum / sampleChunkSize;
        
        // Scale the value to be between 0 and 1 for the blend shape.
        // This scaling factor (e.g., 15) may need tuning.
        const mouthValue = Math.min(1.0, average * 15);
        setMouthOpen(mouthValue);

        requestAnimationFrame(frame); // Continue to the next frame
    }
    
    requestAnimationFrame(frame); // Start the animation
}


// Wait for the DOM to be ready before setting up event listeners
document.addEventListener('DOMContentLoaded', () => {
    const startButton = document.getElementById('start-button');

    startButton.addEventListener('click', () => {
        // 1. Create AudioContext on user gesture
        if (!audioContext) {
            audioContext = new AudioContext();
            audioContext.resume(); // Good practice to resume it
            console.log('AudioContext Initialized.');
        }

        // 2. Connect WebSocket
        if (!ws || ws.readyState === WebSocket.CLOSED) {
            ws = new WebSocket("ws://192.168.1.175:8765");
            ws.binaryType = "arraybuffer";
            
            ws.onopen = () => {
                console.log("WebSocket connected!");
                startButton.textContent = "Connected";
                startButton.disabled = true;
            };
            
            ws.onmessage = async (event) => {
                if (!audioContext) {
                    console.error("AudioContext not initialized. Cannot process audio.");
                    return;
                }
                console.log("[WS] Received audio data");
                const audioData = event.data; // ArrayBuffer of WAV
                
                try {
                    // Use the existing AudioContext to decode the data
                    const buffer = await audioContext.decodeAudioData(audioData);
                    animateMouthFromBuffer(buffer);
                } catch (e) {
                    console.error("Error decoding audio data:", e);
                }
            };
            
            ws.onclose = () => {
                console.log("WebSocket - Closed connection");
                startButton.textContent = "Reconnect";
                startButton.disabled = false;
            };

            ws.onerror = (err) => {
                console.error("WebSocket Error:", err);
            }
        }
    });
});

function autoBlink() {
  const expr = currentVrm.expressionManager;
  if (!expr) return;

  setInterval(() => {
    expr.setValue('blink', 1.0);
    expr.update();

    setTimeout(() => {
      expr.setValue('blink', 0.0);
      expr.update();
    }, 150);
  }, 3000); // every 3 seconds
}

// function startMouthAnimation(duration) {
//     if (!duration || duration <= 0) return;

//     const start = Date.now();
//     const end = start + duration * 1000;

//     const interval = setInterval(() => {
//         const now = Date.now();
//         const progress = (now - start) / (end - start);

//         if (progress >= 1) {
//             clearInterval(interval);
//             setMouthOpen(0);
//             console.log("[VRM] Done speaking.");
//             return;
//         }

//         // Simple oscillation for testing
//         const mouthValue = Math.abs(Math.sin(progress * Math.PI * 4));
//         setMouthOpen(mouthValue);
//     }, 50);
// }

// Stub — replace this with your VRM expression control
function setMouthOpen(value) {
    if (!currentVrm || !currentVrm.expressionManager) return;
    currentVrm.expressionManager.setValue( 'aa', value);
    // console.log(`[VRM] Mouth open level: ${value.toFixed(2)}`);
}

loader.load(

  // URL of the VRM you want to load
  '/models/Sirius.vrm',

  // called when the resource is loaded
  async (gltf) => {
    const vrm = gltf.userData.vrm;

    // calling these functions greatly improves the performance
    VRMUtils.removeUnnecessaryVertices( gltf.scene );
    VRMUtils.combineSkeletons( gltf.scene );
    VRMUtils.combineMorphs( vrm );

    // Disable frustum culling
    vrm.scene.traverse( ( obj ) => {
      obj.frustumCulled = false;
    } );

    currentVrm = vrm;
    console.log( vrm );
    scene.add( vrm.scene );

    // Create mixer after VRM is loaded
    mixer = new THREE.AnimationMixer(vrm.scene);

    // Example: load a BVH animation
    const clip = await loadBVHAnimation('/animations/neutral.bvh', vrm, 1.0); // 1.0 is hips height placeholder
    mixer.clipAction(clip).play();
    autoBlink();
  },

  // called while loading is progressing
  ( progress ) => console.log( 'Loading model...', 100.0 * ( progress.loaded / progress.total ), '%' ),

  // called when loading has errors
  ( error ) => console.error( error )
);

// animate
const clock = new THREE.Clock();
clock.start();

// Camera info display
const camInfo = document.createElement('div');
camInfo.style.position = 'absolute';
camInfo.style.top = '10px';
camInfo.style.left = '10px';
camInfo.style.color = 'white';
camInfo.style.fontFamily = 'monospace';
document.body.appendChild(camInfo);

// Background select
const bgSelect = document.createElement('select');
bgSelect.style.position = 'absolute';
bgSelect.style.top = '40px';
bgSelect.style.left = '10px';
bgSelect.style.background = '#222';
bgSelect.style.color = 'white';
bgSelect.style.fontFamily = 'monospace';
bgSelect.style.padding = '4px';
bgSelect.style.border = '1px solid #555';
bgSelect.style.borderRadius = '4px';
document.body.appendChild(bgSelect);

Object.keys(backgrounds).forEach(name => {
  const option = document.createElement('option');
  option.value = name;
  option.textContent = name;
  bgSelect.appendChild(option);
});

// Load last background choice (if any)
const savedBG = localStorage.getItem('selectedBackground');
if (savedBG && backgrounds[savedBG] !== undefined) {
  bgSelect.value = savedBG;
  setBackground(savedBG);
} else {
  bgSelect.value = 'None';
  setBackground('None');
}

// Save background choice on change
bgSelect.addEventListener('change', e => {
  const selected = e.target.value;
  setBackground(selected);
  localStorage.setItem('selectedBackground', selected);
});

['r','g','b'].forEach(c => {
  const slider = colorSliders[c];
  const saved = localStorage.getItem(`bgColor_${c}`);
  if (saved) slider.value = saved;

  slider.addEventListener('input', () => {
    localStorage.setItem(`bgColor_${c}`, slider.value);
    if (bgSelect.value === 'None') setBackground('None');
  });
});


function animate() {

  requestAnimationFrame( animate );
  const deltaTime = clock.getDelta();

  if (mixer) mixer.update(deltaTime); // animate VRM
  // update vrm components
  if (currentVrm !== undefined) currentVrm.update(deltaTime);
  // Volume-based lip sync
  // if (currentVrm) {
  //     analyser.getByteFrequencyData(dataArray);
  //     let sum = 0;
  //     for (let i = 0; i < dataArray.length; i++) sum += dataArray[i];
  //     const volume = sum / dataArray.length / 128; // normalized 0-1
  //     //currentVrm.blendShapeProxy.setValue("A", volume);
  //     // Example for "A" shape
  //     if (currentVrm?.expressionManager) {
  //         const expr = currentVrm.expressionManager;
  //         expr.setValue('a', volume);  // lowercase 'a' or whatever your blend shape is named
  //         expr.update();
  //     }
  // }

  camInfo.textContent =
  `Camera: ${camera.position.x.toFixed(2)}, ${camera.position.y.toFixed(2)}, ${camera.position.z.toFixed(2)}\n` +
  `Target: ${controls.target.x.toFixed(2)}, ${controls.target.y.toFixed(2)}, ${controls.target.z.toFixed(2)}`;
  // render
  renderer.render( scene, camera );

}

animate();