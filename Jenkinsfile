pipeline {
    agent any
    environment {
        IMAGE = "namanjain524/tomits"
        TAG   = "${env.BUILD_NUMBER}"
    }
    stages {
        stage('Checkout') {
            steps { checkout scm }
        }
        stage('Build and Test') {
            steps {
                sh '''
                    python3 -m venv .ci-venv
                    . .ci-venv/bin/activate
                    pip install -q -r requirements-core.txt pytest
                    python -m compileall -q tomits
                    python -m pytest -q --ignore=tests/test_voice.py --ignore=tests/test_voice_nlu.py
                '''
            }
        }
        stage('Docker Build') {
            steps { sh 'docker build -t $IMAGE:$TAG -t $IMAGE:latest .' }
        }
        stage('Push Image') {
            steps {
                withCredentials([usernamePassword(credentialsId: 'dockerhub',
                                                  usernameVariable: 'U', passwordVariable: 'P')]) {
                    sh '''
                        echo "$P" | docker login -u "$U" --password-stdin
                        docker push $IMAGE:$TAG
                        docker push $IMAGE:latest
                    '''
                }
            }
        }
        stage('Deploy to Minikube') {
            steps {
                sh '''
                    sed "s#DOCKER_USER/tomits:latest#$IMAGE:$TAG#" k8s/deployment.yaml | kubectl apply -f -
                    kubectl apply -f k8s/service.yaml
                    kubectl rollout status deployment/tomits --timeout=120s
                '''
            }
        }
        stage('Verify') {
            steps {
                sh '''
                    kubectl get pods,deployment,service -l app=tomits
                    URL=$(minikube service tomits --url)
                    echo "tomits is at $URL"
                    curl -fsS "$URL/" > /dev/null
                '''
            }
        }
    }
}
