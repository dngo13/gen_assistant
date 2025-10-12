import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm';

// renderer
const renderer = new THREE.WebGLRenderer();
renderer.setSize( window.innerWidth, window.innerHeight );
renderer.setPixelRatio( window.devicePixelRatio );
document.body.appendChild( renderer.domElement );

// camera
const camera = new THREE.PerspectiveCamera( 15.0, window.innerWidth / window.innerHeight, 0.1, 20.0 );
camera.position.set( 0.0, 1.0, 10.0 );

// camera controls
const controls = new OrbitControls( camera, renderer.domElement );
controls.screenSpacePanning = true;
controls.target.set( 0.0, 1.0, 0.0 );
controls.update();

// scene
const scene = new THREE.Scene();

// light
const light = new THREE.DirectionalLight( 0xffffff, Math.PI );
light.position.set( 1.0, 1.0, 1.0 ).normalize();
scene.add( light );

// gltf and vrm
let currentVrm = undefined;
const loader = new GLTFLoader();
loader.crossOrigin = 'anonymous';

loader.register( ( parser ) => {

  return new VRMLoaderPlugin( parser );

} );

loader.load(

  // URL of the VRM you want to load
  'public/models/Sirius.vrm',

  // called when the resource is loaded
  ( gltf ) => {

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

  },

  // called while loading is progressing
  ( progress ) => console.log( 'Loading model...', 100.0 * ( progress.loaded / progress.total ), '%' ),

  // called when loading has errors
  ( error ) => console.error( error )

);

// helpers
// const gridHelper = new THREE.GridHelper( 10, 10 );
// scene.add( gridHelper );

// const axesHelper = new THREE.AxesHelper( 5 );
// scene.add( axesHelper );

// animate
const clock = new THREE.Clock();
clock.start();

function animate() {

  requestAnimationFrame( animate );

  // update vrm components
  if ( currentVrm ) {

    currentVrm.update( clock.getDelta() );

  }

  // render
  renderer.render( scene, camera );

}

animate();