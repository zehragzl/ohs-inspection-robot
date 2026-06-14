import { initializeApp } from "firebase/app";
import { getFirestore } from "firebase/firestore";
import { getAnalytics } from "firebase/analytics";

// Your web app's Firebase configuration
// For Firebase JS SDK v7.20.0 and later, measurementId is optional
const firebaseConfig = {
  apiKey: "AIzaSyCrCwtSY38wtgcWF8NJ5NbexZU1oo69zQ8",
  authDomain: "computer-project-bb33a.firebaseapp.com",
  projectId: "computer-project-bb33a",
  storageBucket: "computer-project-bb33a.firebasestorage.app",
  messagingSenderId: "1064528302648",
  appId: "1:1064528302648:web:2cc03f6289c95a57d80ccd",
  measurementId: "G-N38N8TB8HF"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
const analytics = getAnalytics(app);

// Initialize Cloud Firestore and get a reference to the service
const db = getFirestore(app);

export { db, analytics };
